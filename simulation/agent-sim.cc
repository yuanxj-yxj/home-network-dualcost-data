/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * agent-sim.cc —— 家庭网络智能体协同：发现—执行二元开销仿真
 *
 * 对应理论文档：家庭网络智能体协同承载边界论文/01_理论模型与命题推导.md
 * 验证目标：
 *   命题 1  发现开销的两段律（轻碰撞区指数、退避饱和区线性）
 *   命题 2  执行位置的门限带结构（端 → 家庭 → 云）
 *   命题 3  承载放大系数下界、缓存增益与自限性（Lambda 单峰）
 *
 * 设计要点（决定结果是否可信，勿改）：
 *   1) 发现竞争不手工建模：直接用 ns-3 DCF 的 CSMA/CA + BEB，
 *      固定 CW_min=15（802.11 默认），故 tau 不随 N 变化 —— 这是命题 1 的物理来源。
 *   2) 多播查询用受限广播地址实现：ns-3 对非单播帧按 non-unicast（基本）速率发送，
 *      与真实 Wi-Fi 多播"不做速率自适应"的机制一致，同时规避组播路由配置。
 *   3) 响应延迟取 U(0, W)：与 mDNS 的随机应答延迟一致，避免 N 个节点同时发送的退化碰撞。
 *   4) 云端上下文 C 每次调用全量上传（psi=0），家庭主机侧常驻（不产生 WAN 字节）——
 *      这是 gamma_2 含 C/B_u 项而 gamma_1 不含的直接体现，整个模型张力来源。
 *   5) 五种放置策略在同一 seed 下并行评估，仿真次数从 5x10 降至 10。
 *
 *   空口时长采用"按字节/速率解析计算"（AirtimeFromBytes），不依赖 WifiPhy 的
 *   PhyTxBegin/PhyTxEnd trace 签名，避免跨 ns-3 版本的编译脆弱性。
 *   需要精确统计时，可在 SendRsp/SendDone 处改接 WifiPhy trace。
 *
 * 用法示例：
 *   agent-sim --mode=E1 --N=32 --discovery=multicast --link=wifi5 --seed=1 --out=runs/e1
 *   agent-sim --mode=E2 --N=32 --m=3 --g=16384 --rttMs=30 --bwUpMbps=30 \
 *             --ctxKB=16 --psi=0 --duration=60 --seed=1 --out=runs/e2
 */
#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/bridge-module.h"
#include "ns3/csma-module.h"
#include "ns3/internet-module.h"
#include "ns3/lr-wpan-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/sixlowpan-module.h"
#include "ns3/wifi-module.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <list>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using namespace ns3;

// 执行宿主端口（hub 家用算力主机 / cloud），与终端 60000、目录 60001、编排器 60002 错开
static const uint16_t kExecHubPort = 60003;
static const uint16_t kExecCloudPort = 60004;
// 背景流量端口（E4）：上行 bg→cloud，下行 cloud→bg
static const uint16_t kBgUpPort = 60010;
static const uint16_t kBgDnPort = 60011;

NS_LOG_COMPONENT_DEFINE ("AgentSim");

/* =======================================================================
 * 全局配置
 * ======================================================================= */
struct Cfg
{
  std::string mode = "E1"; // E1 / E2 / E4
  std::string out = "runs/agent";
  std::string link = "wifi5";        // wifi5 / wifi24 / thread
  std::string discovery = "multicast"; // multicast / directory / cache
  std::string policy = "ours"; // ours / allcloud / alllocal / static / oracle / mix
  std::string gdist = "fixed";       // fixed / lognormal（H1 同质假设的松弛）

  uint32_t N = 32;      // 终端智能体总数（命题 1 的自变量）
  double wifiRatio = 0.7; // N_w / N
  uint32_t m = 3;       // 子任务数
  uint32_t g = 16384;   // 子任务粒度（byte）
  uint32_t mtu = 1500;

  double rttCloudMs = 30.0; // r_c（推论 2.1(ii)）
  double rttLanMs = 1.0;    // r_L
  double bwUpMbps = 30.0;   // B_u（推论 2.1(iv)、推论 2.2）
  double bwDnMbps = 300.0;  // B_d
  double bwLanMbps = 400.0; // B_L

  uint32_t ctxKB = 16;   // C：基础上下文
  uint32_t cdeltaKB = 1; // c_δ：每步增量
  uint32_t hdrB = 512;   // h_hdr：协议头
  uint32_t psi = 0;      // 缓存策略 0/1（命题 3(ii)）
  double rho = 0.5;      // ρ = 输出/输入

  // κ 与 f 统一用 GFLOP 单位制：computeS = κ[GFLOP/byte] * g[byte] / f[GFLOP/s]
  // 默认值使 16 KB 子任务在家庭主机上约 35 ms，量级与 7B 量化模型相符；
  // 正式实验须用实物微型床标定后替换（见 02 号文档第 6 节）。
  double kappaGflopsPerByte = 0.0043; // 16 KB 子任务 ≈ 70 GFLOP
  double f0 = 100.0;   // 端侧小模型  100 GFLOP/s
  double f1 = 2000.0;  // 家庭主机     2 TFLOP/s
  double f2 = 50000.0; // 云           50 TFLOP/s

  double respWindowMs = 20.0;     // W：mDNS 随机应答窗口
  double taskTimeoutMs = 2000.0;  // 单子任务等待上限，超时记失败
  double queryTimeoutMs = 60.0;
  uint32_t maxRequery = 5;
  uint32_t nQueries = 50;
  double queryIntervalMs = 20.0;

  std::string ctrlMode = "OfdmRate6Mbps"; // 控制/非单播速率（决定多播发现速率）
  double basicMbps = 6.0;                 // 基本速率，用于发现帧空口时长折算
  std::string bg = "none"; // none / video / gaming / backup
  std::string bgProto = "udp"; // udp（BgApp 无反馈 CBR）/ tcp（OnOff 限速 + NewReno）
  double bwUpMeasMbps = 0.0;   // 网关被动测得的可用上行；0 = 未测量，用标称 bwUpMbps
  bool useMeasUp = false;      // ours 是否也消费实测上行（§6.6 的推荐部署形态）
  double bgScale = 1.0;    // 背景流强度倍率（剂量扫描用：1.0=标称家庭负载）
  double duration = 60.0;
  // 预热期：此时段内不做发现/任务测量，只让终端完成 802.11 关联与 ARP 解析。
  // 依据：实测 N=16 时若测量从 t=0.2 s 开始，个别终端会在关联/ARP 竞争里失败，
  // 其 ARP 条目进入 DEAD 状态，整段测量内所有应答在 ARP 待发队列被静默丢弃
  // （交接文档 5.4-6）。预热是测量方法论的标准做法，不改变被测机制。
  double warmupS = 3.0;
  // 终端关联方式：0=被动扫描（等信标）1=主动探测（发 Probe Request）
  // 被动扫描在 N 较大时可能因信标/关联帧竞争而让个别终端关联状态不完整
  uint32_t activeProbe = 0;
  // 1=把竞争窗口钉在 CW_min（MinCw=MaxCw=15，禁用 BEB）。
  // 命题 1 的指数段以"固定 CW_min、τ=1/(CW_min+1) 不随 N 变化"为前提；
  // 默认的 BEB 会在碰撞后自动放大窗口，把系统拉回近线性区，故默认 0。
  uint32_t pinCw = 0;
  // Wi-Fi 标准：11a / 11n5 / 11n24。
  // 11n 在本树里存在关联状态机残留问题：AP 对个别站点一直停在"已收关联请求但
  // 关联响应未确认成功"的状态（GetStaList 有它、stationManager->IsAssociated 为 false），
  // 于是 ApWifiMac::Receive 丢弃该站点全部上行数据帧（实测 N=16 时每种子固定 1～2 个）。
  // 11a 无 HT/BA 机制，且与命题 1 的"基本速率 DCF"建模口径一致。
  std::string wifiStd = "11n5";
  // 1=打印逐包调试（[QRY-TX]/[PKT-RX]/[ARP-ST]），正式实验保持 0 以免污染日志
  uint32_t verbose = 0;
  uint32_t seed = 1;
};

static Cfg g_cfg;
static Ptr<UniformRandomVariable> g_uv;

/* =======================================================================
 * 单服务台排队（G/G/1）：刻画 W_p，使排队自然发生
 * ======================================================================= */
class ServiceQueue
{
public:
  Time
  Submit (Time now, Time service)
  {
    Time start = Max (now, m_lastFinish);
    m_lastFinish = start + service;
    ++m_count;
    return m_lastFinish;
  }
  Time
  LastFinish () const
  {
    return m_lastFinish;
  }

private:
  Time m_lastFinish = Seconds (0);
  uint32_t m_count = 0;
};

/* =======================================================================
 * 消息格式（应用层自定义，用字符串编码以便解析与调试）
 *   REG|agentId|cap|loc
 *   QRY|seq|cap
 *   RSP|seq|agentId|loc
 *   TASK|seq|agentId|gBytes|execLoc
 *   DONE|seq|agentId|execLoc
 *   REMOTE_TASK（loc=1/2 真实转发到执行宿主，携带 gBytes 与 ctxBytes）
 *   REMOTE_DONE（执行宿主回执，终端据此向编排器上报 DONE）
 * 另：上下文以"纯字节数据块"（无报文头）随 REMOTE_TASK 之后发往同一宿主，
 *     接收端无法解码即丢弃——它只负责让 C 真实占用上行带宽。
 * ======================================================================= */
enum MsgType
{
  MSG_REG = 0,
  MSG_QRY,
  MSG_RSP,
  MSG_TASK,
  MSG_DONE,
  MSG_REMOTE_TASK, // 终端 → 执行宿主（loc=1/2）
  MSG_REMOTE_DONE, // 执行宿主 → 终端
  MSG_BLK_NAK      // 执行宿主 → 终端：数据块不全，请求补发（见 §4.2 可靠传输）
};

struct Msg
{
  MsgType type;
  uint32_t seq;
  uint32_t agentId;
  std::string cap;
  uint32_t loc;      // 执行位置 0/1/2
  uint32_t gBytes;   // 子任务负载
  uint32_t ctxBytes; // 随调用携带的上下文
};

static std::string
Encode (const Msg &m)
{
  std::ostringstream os;
  os << (int) m.type << "|" << m.seq << "|" << m.agentId << "|" << m.cap << "|" << m.loc << "|"
     << m.gBytes << "|" << m.ctxBytes;
  return os.str ();
}

static bool
Decode (const std::string &s, Msg &m)
{
  std::vector<std::string> f;
  std::string cur;
  for (char c : s)
    {
      if (c == '|')
        {
          f.push_back (cur);
          cur.clear ();
        }
      else
        {
          cur += c;
        }
    }
  f.push_back (cur);
  if (f.size () < 7)
    {
      return false;
    }
  m.type = (MsgType) atoi (f[0].c_str ());
  m.seq = (uint32_t) atoi (f[1].c_str ());
  m.agentId = (uint32_t) atoi (f[2].c_str ());
  m.cap = f[3];
  m.loc = (uint32_t) atoi (f[4].c_str ());
  m.gBytes = (uint32_t) atoi (f[5].c_str ());
  m.ctxBytes = (uint32_t) atoi (f[6].c_str ());
  return true;
}

/* =======================================================================
 * 全局计数器（WAN 字节 / 空口占用）
 * ======================================================================= */
static uint64_t g_wanUpBytes = 0;
static uint64_t g_wanDnBytes = 0;
// 真实 WAN 字节（P2P 设备 MacTx 计数）：用于对照解析式 λ，
// 解析式按"最终执行位置"预估，真实值含 ARP、重传与上下文数据块的全部开销
static uint64_t g_wanTxRealB = 0;
static uint64_t g_wanDnRealB = 0;
static void
CntWanTx (Ptr<const Packet> p)
{
  g_wanTxRealB += p->GetSize ();
}
static void
CntWanDn (Ptr<const Packet> p)
{
  g_wanDnRealB += p->GetSize ();
}
// 网关 WAN 出口队列的逐包排队延迟（Enqueue→Dequeue）：用于确认背景流与智能体流
// 是否真的共用同一 FIFO。若共用一个已压满的队列，智能体包的排队延迟必然随之抬升。
static std::map<uint64_t, Time> g_qEnqAt;
static std::map<uint32_t, uint64_t> g_qHist;
static double g_qDelaySumMs = 0.0;
static double g_qDelayMaxMs = 0.0;
static uint64_t g_qN = 0;
static uint64_t g_qBigN = 0;   // 智能体上下文大块（>20 KB）
static double g_qBigSumMs = 0.0;
static uint64_t g_qSmlN = 0;   // 背景流小包
static double g_qSmlSumMs = 0.0;
static void
QEnq (Ptr<const Packet> p)
{
  g_qEnqAt[p->GetUid ()] = Simulator::Now ();
  uint32_t b = p->GetSize () / 4096;
  ++g_qHist[b];
}
static void
QDeq (Ptr<const Packet> p)
{
  auto it = g_qEnqAt.find (p->GetUid ());
  if (it == g_qEnqAt.end ())
    {
      return;
    }
  double d = (Simulator::Now () - it->second).GetMilliSeconds ();
  g_qEnqAt.erase (it);
  g_qDelaySumMs += d;
  g_qDelayMaxMs = std::max (g_qDelayMaxMs, d);
  ++g_qN;
  if (p->GetSize () > 20000)
    {
      g_qBigSumMs += d;
      ++g_qBigN;
    }
  else
    {
      g_qSmlSumMs += d;
      ++g_qSmlN;
    }
}

static uint64_t g_airtimeUs = 0;
static std::vector<double> g_latencyMs;

// 诊断计数（定位"任务发出去没回来"这类问题）
static uint64_t g_taskSent = 0;
static uint64_t g_taskRecv = 0;
static uint64_t g_blkNak = 0;   // NACK 次数（数据块补发请求）
static uint64_t g_blkResend = 0; // 实际补发的次数
static uint64_t g_doneSent = 0;
static uint64_t g_rspRecv = 0;
static uint64_t g_querySent = 0;
static uint32_t g_pktDbg = 0;
static uint64_t g_taskFailed = 0;
static std::vector<double> g_discMs; // 每轮发现时滞（ms，粗粒度留档）
static std::vector<double> g_discUs; // 同一量的微秒值（低 N 时 ms 量化过粗，拟合两段律须用此列）
static uint64_t g_rounds = 0;       // 完成的发现轮数
static uint64_t g_missing = 0;      // 累计未响应数（衡量发现失败）

// 逐终端诊断（定位 5.4-6：为何个别终端始终不应答）
// qry: 该终端收到的查询帧数；rspTx: 该终端发出的应答数；rspRx: 目录侧收到该终端的应答数
static std::map<uint32_t, uint64_t> g_qryRxByAgent;
static std::map<uint32_t, uint64_t> g_rspTxByAgent;
static std::map<uint32_t, uint64_t> g_rspRxByAgent;
static std::map<uint32_t, std::map<int, uint64_t>> g_rspErrByAgent; // SendTo 返回 -1 的 errno
static uint64_t g_dirPktRx = 0;   // 目录套接字收到的报文总数（含各类型）
static std::map<int, uint64_t> g_hubIp4Drop; // hub 的 IP 层丢包原因
static void
CntHubIp4Drop (const Ipv4Header &, Ptr<const Packet>, Ipv4L3Protocol::DropReason r, Ptr<Ipv4>, uint32_t)
{
  ++g_hubIp4Drop[(int) r];
}
static std::map<std::string, uint64_t> g_apRxDrop;
static void
CntApRxDrop (Ptr<const Packet>)
{
  ++g_apRxDrop["ap"];
}
static uint64_t g_apMacRx = 0;    // AP 从 Wi-Fi 侧收到的帧数
static uint64_t g_hubEthMacRx = 0; // hub 以太口从 AP 侧收到的帧数
static void
CntApRx (Ptr<const Packet>)
{
  ++g_apMacRx;
}
static std::map<std::string, uint64_t> g_hubSrcMac;
static void
CntHubEthRx (Ptr<const Packet> p)
{
  ++g_hubEthMacRx;
  EthernetHeader h;
  if (p->PeekHeader (h) > 0)
    {
      std::ostringstream os;
      os << Mac48Address::ConvertFrom (h.GetSource ());
      ++g_hubSrcMac[os.str ()];
    }
}
static std::map<uint32_t, uint64_t> g_arpDropByAgent; // ARP 待发队列满而丢的包（Ipv4Interface::Send 静默路径）
static std::vector<Ptr<ArpCache>> g_staArp;            // 各终端网卡的 ARP 缓存（用于事后核查）

static void
CntArpDrop (uint32_t id, Ptr<const Packet>)
{
  ++g_arpDropByAgent[id];
}

// 逐终端 MAC/PHY 层计数（判定"终端到底有没有把帧发出去"）
// macTx：MAC 交给 PHY 的帧；phyTxBegin：PHY 真正开始发射；phyTxDrop：PHY 丢弃；
// macTxDrop：MAC 层丢弃（队列满/无关联等）
static std::map<uint32_t, uint64_t> g_macTxByAgent;
static std::map<uint32_t, uint64_t> g_phyTxBeginByAgent;
static std::map<uint32_t, uint64_t> g_phyTxDropByAgent;
static std::map<uint32_t, uint64_t> g_macTxDropByAgent;
// UID 精确口径：phyDataTx = 数据帧 PHY 发射次数（MacTx 见过的 UID，含重传），
// phyOtherTx = 非数据帧发射（ACK/BAR 等，Uid 未在 MacTx 中出现）
static std::set<uint64_t> g_macTxUids;
static std::map<uint32_t, uint64_t> g_phyDataTxByAgent;
static std::map<uint32_t, uint64_t> g_phyOtherTxByAgent;
// 应答帧专属口径：SendRsp 时记录应答包 UID，PhyTxBegin 按 UID 归属计数——
// 管理帧（auth/assoc 请求，MacTx 也会计数且重传频繁）不得混入重传统计
static std::map<uint32_t, std::set<uint64_t>> g_rspUids;
static std::map<uint32_t, uint64_t> g_rspPhyTxByAgent;
// 真实空口占用：PhyTxBegin 记时间戳、PhyTxEnd 结算时长（含重传与碰撞重叠）
static std::map<uint32_t, uint64_t> g_txBusyUsByAgent;
static std::map<uint32_t, double> g_lastTxBeginByAgent;
static const uint32_t kApTxId = 9000; // AP 侧专用编号
static uint64_t g_apTxBusyUs = 0;

static void
CntMacTx (uint32_t id, Ptr<const Packet> p)
{
  ++g_macTxByAgent[id];
  // 记录"上层交给 MAC 的帧"的 UID：数据帧重传时 MAC 复用同一 Packet 对象，
  // UID 不变——据此可在 PhyTxBegin 里把"数据帧发射（含重传）"与
  // "非数据帧发射（ACK/BAR 等）"精确分开，消除 retx 口径的系统性偏置。
  g_macTxUids.insert (p->GetUid ());
}
static void
CntMacTxDrop (uint32_t id, Ptr<const Packet>)
{
  ++g_macTxDropByAgent[id];
}
static void
CntPhyTxBegin (uint32_t id, Ptr<const Packet> p, double)
{
  ++g_phyTxBeginByAgent[id];
  uint64_t u = p->GetUid ();
  if (g_rspUids.count (id) && g_rspUids[id].count (u))
    {
      ++g_rspPhyTxByAgent[id];
    }
  if (g_macTxUids.count (u))
    {
      ++g_phyDataTxByAgent[id];
    }
  else
    {
      ++g_phyOtherTxByAgent[id];
    }
  g_lastTxBeginByAgent[id] = Simulator::Now ().GetSeconds ();
}
static void
CntPhyTxEnd (uint32_t id, Ptr<const Packet>)
{
  auto it = g_lastTxBeginByAgent.find (id);
  if (it != g_lastTxBeginByAgent.end ())
    {
      uint64_t us = (uint64_t) ((Simulator::Now ().GetSeconds () - it->second) * 1e6);
      if (id == kApTxId)
        {
          g_apTxBusyUs += us;
        }
      else
        {
          g_txBusyUsByAgent[id] += us;
        }
    }
}
static void
CntPhyTxDrop (uint32_t id, Ptr<const Packet>)
{
  ++g_phyTxDropByAgent[id];
}

// IP 层丢包原因（判定 UDP 交给 IP 之后是在哪一步被丢的）
static std::map<uint32_t, std::map<int, uint64_t>> g_ip4DropByAgent;
static void
CntIp4Drop (uint32_t id,
            const Ipv4Header &,
            Ptr<const Packet>,
            Ipv4L3Protocol::DropReason reason,
            Ptr<Ipv4>,
            uint32_t)
{
  ++g_ip4DropByAgent[id][(int) reason];
}

// UDP 层丢包（最常见：路由查表失败，包根本没交给 IP，因此 IP 层看不到）
static std::map<uint32_t, std::map<int, uint64_t>> g_udpDropByAgent;
static void
CntUdpDrop (uint32_t id, Ptr<const Packet> pkt)
{
  ++g_udpDropByAgent[id][(int) pkt->GetSize ()];
}

static double
AirtimeFromBytes (uint32_t bytes, double rateBps)
{
  return 1e6 * (bytes + 40) * 8.0 / rateBps; // 40 B 为 MAC/PHY 开销近似
}

/* =======================================================================
 * 终端智能体应用
 * ======================================================================= */
class AgentNodeApp : public Application
{
public:
  static TypeId
  GetTypeId (void)
  {
    static TypeId tid = TypeId ("ns3::AgentNodeApp")
                            .SetParent<Application> ()
                            .SetGroupName ("Applications")
                            .AddConstructor<AgentNodeApp> ();
    return tid;
  }

  AgentNodeApp () : m_port (60000) {}

  void Setup (uint32_t agentId, std::string cap, uint32_t loc, Ipv4Address dirAddr, uint16_t port,
              double rateBps)
  {
    m_agentId = agentId;
    m_cap = cap;
    m_loc = loc;
    m_dirAddr = dirAddr;
    m_port = port;
    m_rateBps = rateBps;
  }

  // 执行宿主地址（loc=1 家用 hub，loc=2 云）；端口固定 60003/60004
  void
  SetExecHosts (Ipv4Address hubAddr, Ipv4Address cloudAddr)
  {
    m_execHub = hubAddr;
    m_execCloud = cloudAddr;
  }

  Ipv4Address
  GetAddress () const
  {
    return m_addr;
  }
  uint32_t
  GetAgentId () const
  {
    return m_agentId;
  }
  uint32_t
  GetLoc () const
  {
    return m_loc;
  }
  std::string
  GetCap () const
  {
    return m_cap;
  }

private:
  void
  StartApplication (void) override
  {
    m_socket = Socket::CreateSocket (GetNode (), UdpSocketFactory::GetTypeId ());
    m_socket->Bind (InetSocketAddress (Ipv4Address::GetAny (), m_port));
    m_socket->SetAllowBroadcast (true);
    m_socket->SetRecvCallback (MakeCallback (&AgentNodeApp::HandleRead, this));
    m_socket->TraceConnectWithoutContext ("Drop", MakeBoundCallback (&CntUdpDrop, m_agentId));

    Ptr<Ipv4> ipv4 = GetNode ()->GetObject<Ipv4> ();
    m_addr = ipv4->GetAddress (1, 0).GetLocal ();

    // 开机注册（directory / cache 模式计入一次性开销）
    Simulator::Schedule (MilliSeconds (1 + (m_agentId % 50)), &AgentNodeApp::SendReg, this);
  }

  void
  StopApplication (void) override
  {
    if (m_socket)
      {
        m_socket->Close ();
        m_socket = nullptr;
      }
  }

  void
  SendReg (void)
  {
    Msg m{MSG_REG, 0, m_agentId, m_cap, m_loc, 0, 0};
    std::string s = Encode (m);
    Ptr<Packet> p = Create<Packet> ((uint8_t *) s.c_str (), s.size ());
    m_socket->SendTo (p, 0, InetSocketAddress (m_dirAddr, m_dirPort));
  }

  void
  HandleRead (Ptr<Socket> socket)
  {
    Address from;
    Ptr<Packet> pkt;
    while ((pkt = socket->RecvFrom (from)))
      {
        uint32_t n = pkt->GetSize ();
        std::vector<uint8_t> buf (n + 1, 0);
        pkt->CopyData (buf.data (), n);
        Msg m;
        if (!Decode (std::string ((char *) buf.data ()), m))
          {
            continue;
          }
        if (g_cfg.verbose && m_agentId == 0 && g_pktDbg < 6)
          {
            ++g_pktDbg;
            std::cerr << "[PKT-RX] id=0 t=" << Simulator::Now ().GetSeconds ()
                      << " type=" << (int) m.type << " cap=" << m.cap << " mycap=" << m_cap
                      << "\n";
          }
        if (m.type == MSG_QRY && m.cap == m_cap)
          {
            ++g_qryRxByAgent[m_agentId];
            if (g_cfg.verbose && g_qryRxByAgent[m_agentId] == 1)
              {
                std::cerr << "[QRY-RX] id=" << m_agentId << " from="
                          << InetSocketAddress::ConvertFrom (from).GetIpv4 () << " self=" << m_addr
                          << "\n";
              }
            // mDNS 式随机应答延迟 U(0, W)；真实竞争由 MAC 层 DCF 产生。
            // 注意用 Seconds(d/1000) 而非 MilliSeconds(d)：后者参数为整数毫秒，
            // 会把 W=1 ms 内的抽样全部截断为 0（实测 W=0 与 W=1 结果逐位相同即此故）。
            double d = g_uv->GetValue (0.0, g_cfg.respWindowMs);
            Simulator::Schedule (Seconds (d / 1000.0), &AgentNodeApp::SendRsp, this, m.seq, from);
          }
        else if (m.type == MSG_TASK && m.agentId == m_agentId)
          {
            Execute (m, from);
          }
        else if (m.type == MSG_REMOTE_DONE && m.agentId == m_agentId)
          {
            OnRemoteDone (m.seq);
          }
        else if (m.type == MSG_BLK_NAK)
          {
            ResendBlocks (m.seq);
          }
      }
  }

  void
  SendRsp (uint32_t seq, Address from)
  {
    Msg m{MSG_RSP, seq, m_agentId, m_cap, m_loc, 0, 0};
    std::string s = Encode (m);
    Ptr<Packet> p = Create<Packet> ((uint8_t *) s.c_str (), s.size ());
    g_airtimeUs += (uint64_t) AirtimeFromBytes (s.size (), m_rateBps);
    g_rspUids[m_agentId].insert (p->GetUid ());
    ++g_rspTxByAgent[m_agentId];
    if (g_cfg.verbose && g_rspTxByAgent[m_agentId] == 1)
      {
        // 用 ifIndex=1 直接取网卡接口（不能用 GetDevice(1)：那是 loopback）
        Ptr<Ipv4L3Protocol> ip = GetNode ()->GetObject<Ipv4L3Protocol> ();
        Ptr<ArpCache> ac = ip->GetInterface (1)->GetArpCache ();
        Ipv4Address dip = InetSocketAddress::ConvertFrom (from).GetIpv4 ();
        ArpCache::Entry *e = ac->Lookup (dip);
        std::cerr << "[ARP-ST] id=" << m_agentId << " node=" << GetNode ()->GetId () << " cache="
                  << (void *) PeekPointer (ac) << " dst=" << dip << " exists=" << (e != nullptr);
        if (e)
          {
            std::cerr << " alive=" << e->IsAlive () << " wait=" << e->IsWaitReply ()
                      << " dead=" << e->IsDead () << " mac=" << e->GetMacAddress ();
          }
        std::cerr << "\n";
      }
    int rc = m_socket->SendTo (p, 0, from);
    if (rc < 0)
      {
        ++g_rspErrByAgent[m_agentId][(int) m_socket->GetErrno ()];
      }
  }

  /* 数据块统一带 9 字节头："%" + 8 位零填充 seq。
   * 早期版本块是裸字节（无标识），宿主只能按"队首任务"累计——多 agent 并发时
   * 不同任务的块交错到达，字节被记到错误的任务上，表现为 25% 的任务"缺块"
   * （实测 37/150 触发补发、WAN 字节虚高 27%）。加头后归属由 seq 决定，
   * 不再依赖到达顺序。 */
  void
  SendBlocks (uint32_t seq, uint32_t upB, Address dst)
  {
    static const uint32_t kChunk = 1200;
    char hdr[10];
    snprintf (hdr, sizeof hdr, "%%%08u", seq);
    while (upB > 0)
      {
        uint32_t c = (upB < kChunk) ? upB : kChunk;
        Ptr<Packet> blk = Create<Packet> ((uint8_t *) hdr, 9);
        blk->AddAtEnd (Create<Packet> (c));
        m_socket->SendTo (blk, 0, dst);
        upB -= c;
      }
  }

  void
  Execute (const Msg &m, Address from)
  {
    // 服务时间的来源（2026-10-21 改造，勿退回解析注入）：
    //   loc=0：终端本地计算，κ·g/f0 后经本地单服务台排队（代表终端 CPU 独占，
    //          家用设备上智能体与用户应用争用同一 CPU，故串行化是合理近似）；
    //   loc=1/2：**真实转发**到执行宿主（hub / cloud 上的 ExecHostApp），
    //          任务报文与上下文数据块按真实字节数经 ns-3 拓扑发送，
    //          RTT、上行带宽、宿主排队全部由拓扑自然产生。
    // 此前把 r_c、C/B_u 直接加进服务时间（解析注入），会使 E2 的门限位置
    // 与理论闭式自证、并使 E4 的"网关排队随 N 上升"（假设 H3）无法被检验。
    ++g_taskRecv;
    if (m.loc != 0)
      {
        Ipv4Address host = (m.loc == 1) ? m_execHub : m_execCloud;
        uint16_t hport = (m.loc == 1) ? kExecHubPort : kExecCloudPort;
        m_await[m.seq] = from;
        Msg t = m;
        t.type = MSG_REMOTE_TASK;
        std::string s = Encode (t);
        Ptr<Packet> p = Create<Packet> ((uint8_t *) s.c_str (), s.size ());
        m_socket->SendTo (p, 0, InetSocketAddress (host, hport));
        // 数据面：子任务输入必须真实上传，否则 λ 与模型不符（模型里 WAN_up = g + C + h_hdr）。
        //   loc=1：只传 g（上下文在家庭主机常驻，不走 WAN）；
        //   loc=2：传 C + g（云端无状态，每次重传上下文）。
        // 分块 1200 B（≈MSS）：早期用 60000 B 单块，会被 IPv4 分成 ~41 个片，
        // 任一片丢失即整块丢弃，且瞬时写满 UDP 发送缓冲——实测几乎每个任务都要补发
        // 一次（134/150），把重传开销错误地放大成 2 倍带宽。按 MSS 分段后重传只在
        // 真实拥塞下触发，与 QUIC 的行为一致。
        uint32_t upB = m.gBytes + ((m.loc == 2) ? m.ctxBytes : 0);
        // 记下补发所需的三要素（宿主 NACK 时按原样重发，见 ExecHostApp::CheckNack）
        m_rsAddr[m.seq] = InetSocketAddress (host, hport);
        m_rsBytes[m.seq] = upB;
        SendBlocks (m.seq, upB, InetSocketAddress (host, hport));
        return;
      }
    double f = g_cfg.f0;
    double computeS = g_cfg.kappaGflopsPerByte * m.gBytes / f; // GFLOP / (GFLOP/s) = s
    Time finish = m_queue.Submit (Simulator::Now (), Seconds (computeS));
    Simulator::Schedule (finish - Simulator::Now (), &AgentNodeApp::SendDone, this, m.seq, from);
  }

  /* 补发数据块（响应宿主 MSG_BLK_NAK）
   * 上下文门控要求 C+g 全到才开算；出口队列溢出丢块后若无重传，任务会永久等待。
   * 这里按原样整块重发（不做选择性重传：子任务只有 1–2 个块，代价可忽略）。 */
  void
  ResendBlocks (uint32_t seq)
  {
    auto it = m_rsBytes.find (seq);
    if (it == m_rsBytes.end ())
      {
        return;
      }
    SendBlocks (seq, it->second, m_rsAddr[seq]);
    ++g_blkResend;
  }

  // 执行宿主回执 → 向编排器上报完成（回执的 from 即原编排器地址，见 m_await）
  void
  OnRemoteDone (uint32_t seq)
  {
    auto it = m_await.find (seq);
    if (it == m_await.end ())
      {
        return;
      }
    Address orch = it->second;
    m_await.erase (it);
    SendDone (seq, orch);
  }

  void
  SendDone (uint32_t seq, Address from)
  {
    ++g_doneSent;
    Msg m{MSG_DONE, seq, m_agentId, m_cap, m_loc, 0, 0};
    std::string s = Encode (m);
    Ptr<Packet> p = Create<Packet> ((uint8_t *) s.c_str (), s.size ());
    m_socket->SendTo (p, 0, from);
  }

  uint32_t m_agentId{0};
  std::string m_cap;
  uint32_t m_loc{0};
  Ipv4Address m_dirAddr;
  Ipv4Address m_addr;
  Ipv4Address m_execHub;   // 家庭算力主机（loc=1 执行宿主）
  Ipv4Address m_execCloud; // 云（loc=2 执行宿主）
  std::map<uint32_t, Address> m_await; // seq → 编排器地址（等待宿主回执）
  // 补发用：宿主 NACK 时按原地址与原始字节数重发（见 ResendBlocks）
  std::map<uint32_t, Address> m_rsAddr;   // seq → 宿主地址
  std::map<uint32_t, uint32_t> m_rsBytes; // seq → 该任务上传字节数（g 或 C+g）
  uint16_t m_port{60000};    // 本节点接收 QRY/TASK 的端口
  uint16_t m_dirPort{60001}; // 家庭主机上的目录端口
  double m_rateBps{1e6};
  Ptr<Socket> m_socket;
  ServiceQueue m_queue;
};
NS_OBJECT_ENSURE_REGISTERED (AgentNodeApp);

/* =======================================================================
 * 能力目录（驻留于家庭算力主机）
 * ======================================================================= */
class AgentDirApp : public Application
{
public:
  static TypeId
  GetTypeId (void)
  {
    static TypeId tid = TypeId ("ns3::AgentDirApp")
                            .SetParent<Application> ()
                            .SetGroupName ("Applications")
                            .AddConstructor<AgentDirApp> ();
    return tid;
  }

  void
  Setup (uint16_t port)
  {
    m_port = port;
  }

  const std::vector<Ptr<AgentNodeApp>> &
  Registry (const std::string &cap) const
  {
    auto it = m_reg.find (cap);
    return (it != m_reg.end ()) ? it->second : m_empty;
  }

  uint32_t
  RegBytes () const
  {
    return m_regBytes;
  }

private:
  void
  StartApplication (void) override
  {
    m_socket = Socket::CreateSocket (GetNode (), UdpSocketFactory::GetTypeId ());
    m_socket->Bind (InetSocketAddress (Ipv4Address::GetAny (), m_port));
    m_socket->SetRecvCallback (MakeCallback (&AgentDirApp::HandleRead, this));
  }

  void
  StopApplication (void) override
  {
    if (m_socket)
      {
        m_socket->Close ();
        m_socket = nullptr;
      }
  }

  void
  HandleRead (Ptr<Socket> socket)
  {
    Address from;
    Ptr<Packet> pkt;
    while ((pkt = socket->RecvFrom (from)))
      {
        ++g_dirPktRx;
        m_regBytes += pkt->GetSize ();
        uint32_t n = pkt->GetSize ();
        std::vector<uint8_t> buf (n + 1, 0);
        pkt->CopyData (buf.data (), n);
        Msg m;
        if (!Decode (std::string ((char *) buf.data ()), m))
          {
            continue;
          }
        if (m.type == MSG_REG)
          {
            m_reg[m.cap] = {}; // 注册条目计入目录；查询时由编排器直查
          }
      }
  }

  uint16_t m_port{60000};
  Ptr<Socket> m_socket;
  std::map<std::string, std::vector<Ptr<AgentNodeApp>>> m_reg;
  std::vector<Ptr<AgentNodeApp>> m_empty;
  uint32_t m_regBytes{0};
};
NS_OBJECT_ENSURE_REGISTERED (AgentDirApp);

/* =======================================================================
 * 远程执行宿主（家庭算力主机 / 云）
 *
 * 存在意义：把 gamma 从"解析注入"改为"真实转发"。终端收到 loc=1/2 的子任务后
 * 把任务与上下文按真实字节发往执行宿主，服务时间在宿主侧排队计算，
 * 使 RTT、上行带宽、排队全部由 ns-3 拓扑自然产生——
 * 这是 E2（门限带实测位置）、E3（放大系数）、E4（网关排队随 N 上升，假设 H3）
 * 能够被检验的前提。此前把 r_c、C/B_u 直接加进服务时间，等于让实验自证模型。
 * ======================================================================= */
class ExecHostApp : public Application
{
public:
  static TypeId
  GetTypeId (void)
  {
    static TypeId tid = TypeId ("ns3::ExecHostApp")
                            .SetParent<Application> ()
                            .AddConstructor<ExecHostApp> ();
    return tid;
  }

  void
  Setup (uint16_t port, double fGflops)
  {
    m_port = port;
    m_f = fGflops;
  }

  uint64_t
  TaskRx (void) const
  {
    return m_taskRx;
  }

protected:
  void
  StartApplication (void) override
  {
    m_socket = Socket::CreateSocket (GetNode (), UdpSocketFactory::GetTypeId ());
    m_socket->Bind (InetSocketAddress (Ipv4Address::GetAny (), m_port));
    m_socket->SetRecvCallback (MakeCallback (&ExecHostApp::HandleRead, this));
    Simulator::Schedule (MilliSeconds (20), &ExecHostApp::CheckNack, this);
  }

  /* 数据块缺失检测（可靠传输的最小模拟）
   * 背景：上下文门控要求 C+g 全部到达才开算。原实现只发一次、无重传，
   * 一旦出口队列溢出丢掉一个块，该任务就永远等不到数据——整轮挂起，
   * 表现为"任务发送数远小于配额"（实测 s2..s5 仅 84/150）。
   * 真实的 QUIC/TCP 会重传，故此处补一个 NACK：缺块超过 50 ms 就请发送端补发，
   * 上限 40 次（超过则判该任务失败，避免死循环）。 */
  void
  CheckNack (void)
  {
    for (auto &kv : m_need)
      {
        uint32_t seq = kv.first;
        if (m_computed.count (seq))
          {
            continue;
          }
        auto itg = m_got.find (seq);
        if (itg == m_got.end () || itg->second >= kv.second)
          {
            continue;
          }
        double since = (m_lastRx.count (seq) ? (Simulator::Now () - m_lastRx[seq]).GetSeconds ()
                                             : 1.0);
        if (since < 0.05)
          {
            continue;
          }
        uint32_t &n = m_nack[seq];
        if (n >= 40)
          {
            continue;
          }
        ++n;
        ++g_blkNak;
        Msg m{MSG_BLK_NAK, seq, 0, "", 0, 0, 0};
        std::string s = Encode (m);
        Ptr<Packet> p = Create<Packet> ((uint8_t *) s.c_str (), s.size ());
        m_socket->SendTo (p, 0, m_from[seq]);
        m_lastRx[seq] = Simulator::Now (); // 退避一个检测周期，避免每个 tick 都发
      }
    Simulator::Schedule (MilliSeconds (20), &ExecHostApp::CheckNack, this);
  }

  void
  StopApplication (void) override
  {
    if (m_socket)
      {
        m_socket->Close ();
        m_socket = nullptr;
      }
  }

  void
  HandleRead (Ptr<Socket> socket)
  {
    Address from;
    Ptr<Packet> pkt;
    while ((pkt = socket->RecvFrom (from)))
      {
        uint32_t n = pkt->GetSize ();
        std::vector<uint8_t> buf (n + 1, 0);
        pkt->CopyData (buf.data (), n);
        Msg m;
        if (Decode (std::string ((char *) buf.data ()), m) && m.type == MSG_REMOTE_TASK)
          {
            ++m_taskRx;
            m_ctxBytesIn += m.ctxBytes;
            m_gOfSeq[m.seq] = m.gBytes;
            m_from[m.seq] = from;
            m_agentOfSeq[m.seq] = m.agentId;
            // 计算的前置条件：该执行位置**实际需要上传**的字节必须全部到达。
            //   loc=1（家庭主机）：上下文常驻，只传 g；
            //   loc=2（云，无状态）：传 C + g。
            // 此前版本收到控制报文即开算，上下文数据块只被计数、不参与判据——
            // 一旦 WAN 上行被背景流挤占（E4），块被丢弃/延迟而任务时延毫无反应，
            // 等于把"云端无状态、必须重传上下文"这一模型张力在实现里抹掉了。
            m_need[m.seq] = m.gBytes + ((m.loc == 2) ? m.ctxBytes : 0);
            m_got[m.seq] = 0;
            m_order.push_back (m.seq);
            if (m_need[m.seq] == 0)
              {
                TryCompute (m.seq);
              }
            continue;
          }
        if (n == 0)
          {
            continue;
          }
        // 数据块：优先按块头（"%" + seq）归属；无头的老格式回退到队首归属
        if (n > 9 && buf[0] == '%')
          {
            uint32_t sq = (uint32_t) atoi (std::string ((char *) buf.data () + 1, 8).c_str ());
            auto itn = m_need.find (sq);
            if (itn != m_need.end () && !m_computed.count (sq))
              {
                m_got[sq] += (n - 9);
                m_lastRx[sq] = Simulator::Now ();
                if (m_got[sq] >= itn->second)
                  {
                    m_order.remove (sq);
                    TryCompute (sq);
                  }
              }
            continue;
          }
        while (!m_order.empty ())
          {
            uint32_t s = m_order.front ();
            auto it = m_got.find (s);
            if (it == m_got.end ())
              {
                m_order.pop_front ();
                continue;
              }
            it->second += n;
            m_lastRx[s] = Simulator::Now ();
            if (it->second >= m_need[s])
              {
                m_order.pop_front ();
                TryCompute (s);
              }
            break;
          }
      }
  }

  void
  TryCompute (uint32_t seq)
  {
    auto itg = m_gOfSeq.find (seq);
    if (itg == m_gOfSeq.end ())
      {
        return;
      }
    m_computed.insert (seq);
    double computeS = g_cfg.kappaGflopsPerByte * itg->second / m_f;
    Time finish = m_queue.Submit (Simulator::Now (), Seconds (computeS));
    Simulator::Schedule (finish - Simulator::Now (), &ExecHostApp::SendResult, this, seq,
                         m_agentOfSeq[seq], m_from[seq]);
  }

  void
  SendResult (uint32_t seq, uint32_t agentId, Address from)
  {
    ++m_taskDone;
    // 数据面回程：结果体积 ρ·g（模型里 WAN_dn = ρg），真实占用下行带宽。
    // 同样按 60000 B 分块（IPv4 数据报上限，见 Execute 处注释）
    auto it = m_gOfSeq.find (seq);
    if (it != m_gOfSeq.end ())
      {
        uint32_t dnB = (uint32_t) (g_cfg.rho * it->second);
        static const uint32_t kChunk = 1200;
        while (dnB > 0)
          {
            uint32_t c = (dnB < kChunk) ? dnB : kChunk;
            Ptr<Packet> r = Create<Packet> (c);
            m_socket->SendTo (r, 0, from);
            dnB -= c;
          }
        m_gOfSeq.erase (it);
      }
    Msg m{MSG_REMOTE_DONE, seq, agentId, "", 0, 0, 0};
    std::string s = Encode (m);
    Ptr<Packet> p = Create<Packet> ((uint8_t *) s.c_str (), s.size ());
    m_socket->SendTo (p, 0, from);
  }

  uint16_t m_port{60003};
  double m_f{2.0}; // GFLOP/s
  Ptr<Socket> m_socket;
  ServiceQueue m_queue;
  uint64_t m_taskRx{0};
  uint64_t m_taskDone{0};
  uint64_t m_ctxBytesIn{0};
  std::map<uint32_t, uint32_t> m_gOfSeq;      // seq → 子任务负载（用于回程 ρg）
  std::map<uint32_t, uint32_t> m_need;        // seq → 需到达字节（g + C）
  std::map<uint32_t, uint32_t> m_got;         // seq → 已到达字节
  std::map<uint32_t, Time> m_lastRx;          // seq → 最近收到数据的时刻（NACK 判据）
  std::map<uint32_t, uint32_t> m_nack;        // seq → 已发 NACK 次数
  std::set<uint32_t> m_computed;              // 已开算的 seq
  std::map<uint32_t, Address> m_from;         // seq → 来源（回执地址）
  std::map<uint32_t, uint32_t> m_agentOfSeq;  // seq → agentId
  std::list<uint32_t> m_order;                // 到达顺序（数据块按序归属）
};
NS_OBJECT_ENSURE_REGISTERED (ExecHostApp);

/* =======================================================================
 * 背景流量（E4）：家庭侧真实背景负载
 * -----------------------------------------------------------------------
 * 动机：混合负载是"承载边界"最容易被质疑的地方——判据若只在空载下成立，
 * 工程价值有限。E4 用三类典型家庭背景流检验门限是否漂移：
 *   video  ：4K 点播，下行 20 Mbps + 上行 0.5 Mbps（播放控制/心跳）
 *   gaming ：云游戏，下行 8 Mbps + 上行 6 Mbps（交互帧），小包 300 B
 *   backup ：云备份，上行 28 Mbps（几乎独占 B_u=30 Mbps）
 * 关键建模点：只有"上行"背景流会占用 B_u，从而进入 γ₂ = C/B_u + r_c；
 * 下行背景流走的是另一方向的链路容量，按模型不改变 γ₂（见 §7 局限：WAN 对称近似）。
 * 因此 E4 的预期是分层的：backup 显著劣化云侧、gaming 轻微、video 几乎无影响。
 * ======================================================================= */
class BgApp : public Application
{
public:
  static TypeId
  GetTypeId (void)
  {
    static TypeId tid = TypeId ("ns3::BgApp")
                            .SetParent<Application> ()
                            .SetGroupName ("Applications")
                            .AddConstructor<BgApp> ();
    return tid;
  }

  /// sender=true 时按 rateMbps 持续发包到 peer:port；sender=false 时只收不处理
  void
  Setup (uint16_t port, Ipv4Address peer, double rateMbps, uint32_t pktB, bool sender,
         double startS)
  {
    m_port = port;
    m_peer = peer;
    m_rateMbps = rateMbps;
    m_pktB = pktB;
    m_sender = sender;
    m_startS = startS;
  }

  uint64_t
  Bytes (void) const
  {
    return m_bytes;
  }

protected:
  void
  StartApplication (void) override
  {
    m_socket = Socket::CreateSocket (GetNode (), UdpSocketFactory::GetTypeId ());
    if (m_sender)
      {
        m_socket->Bind ();
        if (m_rateMbps > 0)
          {
            Simulator::Schedule (Seconds (m_startS), &BgApp::SendOne, this);
          }
      }
    else
      {
        m_socket->Bind (InetSocketAddress (Ipv4Address::GetAny (), m_port));
        m_socket->SetRecvCallback (MakeCallback (&BgApp::HandleRead, this));
      }
  }

  void
  StopApplication (void) override
  {
    if (m_socket)
      {
        m_socket->Close ();
        m_socket = nullptr;
      }
  }

  void
  SendOne (void)
  {
    if (Simulator::Now ().GetSeconds () >= g_cfg.duration)
      {
        return;
      }
    Ptr<Packet> p = Create<Packet> (m_pktB);
    m_socket->SendTo (p, 0, InetSocketAddress (m_peer, m_port));
    m_bytes += m_pktB;
    double intervalS = (double) m_pktB * 8.0 / (m_rateMbps * 1e6);
    Simulator::Schedule (Seconds (intervalS), &BgApp::SendOne, this);
  }

  void
  HandleRead (Ptr<Socket> socket)
  {
    Ptr<Packet> pkt;
    Address from;
    while ((pkt = socket->RecvFrom (from)))
      {
        m_bytes += pkt->GetSize ();
      }
  }

  uint16_t m_port{60010};
  Ipv4Address m_peer;
  double m_rateMbps{0.0};
  uint32_t m_pktB{1400};
  bool m_sender{false};
  double m_startS{3.0};
  uint64_t m_bytes{0};
  Ptr<Socket> m_socket;
};
NS_OBJECT_ENSURE_REGISTERED (BgApp);

/* =======================================================================
 * 编排器：任务图生成 → 发现 → 放置 → 分发 → 收集
 * ======================================================================= */
class OrchestratorApp : public Application
{
public:
  static TypeId
  GetTypeId (void)
  {
    static TypeId tid = TypeId ("ns3::OrchestratorApp")
                            .SetParent<Application> ()
                            .SetGroupName ("Applications")
                            .AddConstructor<OrchestratorApp> ();
    return tid;
  }

  void
  Setup (uint16_t port, const std::vector<Ptr<AgentNodeApp>> &agents, Ipv4Address self,
         double rateBps)
  {
    m_port = port;       // 编排器自身接收端口（与目录端口错开，避免同节点绑定冲突）
    m_agentPort = 60000; // 终端智能体接收端口
    m_agents = agents;
    m_self = self;
    m_rateBps = rateBps;
  }
  void
  SetBroadcast (Ipv4Address b)
  {
    m_bcast = b;
  }

  /* 理论文档命题 2 的闭式门限：a_p、gamma_p 按 3.3 节定义 */
  void
  Coeffs (double a[3], double gm[3]) const
  {
    // useMeasUp=1 时按网关实测可用上行建模（§6.6 的部署形态）；默认仍用标称值
    double bu = (g_cfg.useMeasUp && g_cfg.bwUpMeasMbps > 0.0) ? g_cfg.bwUpMeasMbps
                                                              : g_cfg.bwUpMbps;
    a[0] = g_cfg.kappaGflopsPerByte / g_cfg.f0;
    a[1] = g_cfg.kappaGflopsPerByte / g_cfg.f1 + 8.0 / (g_cfg.bwLanMbps * 1e6);
    a[2] = g_cfg.kappaGflopsPerByte / g_cfg.f2 + 8.0 / (bu * 1e6) +
           g_cfg.rho * 8.0 / (g_cfg.bwDnMbps * 1e6);
    gm[0] = 0.0;
    gm[1] = g_cfg.rttLanMs / 2000.0;
    gm[2] = (g_cfg.ctxKB * 1024.0 + g_cfg.hdrB) / (bu * 1e6 / 8.0) +
            g_cfg.rttCloudMs / 1000.0;
  }

  double
  GStar (uint32_t p, uint32_t q) const
  {
    double a[3], gm[3];
    Coeffs (a, gm);
    double den = a[p] - a[q];
    if (den <= 1e-12)
      {
        return 1e18; // A1 不成立：门限不存在（退化情形，见推论 2.2）
      }
    return (gm[q] - gm[p]) / den;
  }

  /* 同一套系数，但上行取"网关实测可用带宽"而非标称值（thresh 基线用） */
  void
  CoeffsWithUp (double a[3], double gm[3], double buMbps) const
  {
    Coeffs (a, gm);
    if (buMbps <= 0.0)
      {
        return;
      }
    a[2] = g_cfg.kappaGflopsPerByte / g_cfg.f2 + 8.0 / (buMbps * 1e6) +
           g_cfg.rho * 8.0 / (g_cfg.bwDnMbps * 1e6);
    gm[2] = (g_cfg.ctxKB * 1024.0 + g_cfg.hdrB) / (buMbps * 1e6 / 8.0) +
            g_cfg.rttCloudMs / 1000.0;
  }

  uint32_t
  Place (uint32_t gBytes, const std::string &policy) const  {
    if (policy == "allcloud")
      {
        return 2;
      }
    if (policy == "alllocal")
      {
        return 0;
      }
    if (policy == "static")
      {
        return (gBytes < 8192) ? 0 : 2; // theta = 8 KB，模拟工业界静态配置
      }
    if (policy == "thresh")
      {
        /* 外部基线（[15] 式单智能体回退门限）：
         * 只有一个家庭↔云门限，且用网关被动测得的可用上行 B̂_u 代入；
         * 不含 g1* 段（端侧）、不含并发/m 修正——即"忽略批内协同"的对照物。 */
        double bu = (g_cfg.bwUpMeasMbps > 0.0) ? g_cfg.bwUpMeasMbps : g_cfg.bwUpMbps;
        double a[3], gm[3];
        CoeffsWithUp (a, gm, bu);
        double den = a[1] - a[2];
        if (den <= 1e-12)
          {
            return 1; // 云永不占优：全留家庭（推论 2.2 的退化情形）
          }
        double thKB = (gm[2] - gm[1]) / den / 1024.0;
        return ((gBytes / 1024.0) > thKB) ? 2 : 1;
      }
    // 默认 ours：按门限带结构放置
    double g1 = GStar (0, 1);
    double g2 = GStar (1, 2);
    if (gBytes < g1)
      {
        return 0;
      }
    if (gBytes < g2)
      {
        return 1;
      }
    return 2;
  }

  /* ORACLE：一轮 m 个子任务的放置离线穷举（3^m），给出"批完成时间"最优的上界。
   * 与 ours 的区别正是"忽略排队 vs 显式建模排队"：
   *   批到达时每个宿主串行服务，故该批在 p 上的完成时间 = Σ_{i∈S_p}(a_p g_i + γ_p)；
   *   取各宿主的最大值（makespan），穷举全部 3^m 个指派取最小。
   * m=3 时 27 种、m=5 时 243 种，开销可忽略。这就是正文所说"判据距最优的间隙"的参照。
   */
  std::vector<uint32_t>
  PlaceOracle (const std::vector<uint32_t> &gs) const
  {
    double a[3], gm[3];
    Coeffs (a, gm);
    const size_t n = gs.size ();
    std::vector<uint32_t> best (n, 2);
    double bestMk = 1e18;
    uint64_t total = 1;
    for (size_t i = 0; i < n; ++i)
      {
        total *= 3;
      }
    std::vector<uint32_t> asg (n, 0);
    for (uint64_t code = 0; code < total; ++code)
      {
        uint64_t c = code;
        double load[3] = {0.0, 0.0, 0.0};
        for (size_t i = 0; i < n; ++i)
          {
            asg[i] = (uint32_t) (c % 3);
            c /= 3;
            load[asg[i]] += a[asg[i]] * gs[i] + gm[asg[i]];
          }
        double mk = std::max (load[0], std::max (load[1], load[2]));
        if (mk < bestMk - 1e-12)
          {
            bestMk = mk;
            best = asg;
          }
      }
    return best;
  }

  /* MIX：批内混排的在线贪心（O(m log m)），把逐点门限判据推广到整批 m 个子任务。
   *
   * 动机（E5 实测，表 6）：ours 逐点套门限带，无视同批其余子任务已在某宿主上形成
   * 的串行负载。16 KB/m=3 时判据把三个子任务全放家庭主机（P50=74 ms），而 ORACLE
   * 把其中一个分流到云（P50=44 ms）——批内协同放置可回收 41% 时延，是判据与最优
   * 之间最大的单项间隙；m=5 时间隙扩大到 110%。
   *
   * 算法：与 ORACLE **完全相同的代价模型**（同一组 a_p、γ_p，同一串行服务假设），
   * 只把 3^m 穷举换成 LPT 式贪心——粒度降序，每个子任务放入"最早完成"的执行位置
   * （load[p] + a_p·g_i + γ_p 最小者）。性质：
   *   - m=1 时退化为逐点 argmin_p T_p(g)，在 A1+A2 下即门限带放置本身
   *     （单交叉引理：T_0<T_1⟺g<g1*，T_1<T_2⟺g<g2*）——故 mix 是判据的批推广，
   *     不是另一种启发式；
   *   - 与 ORACLE 的差别只在搜索：多项式贪心 vs 指数穷举，二者之差可实验度量。
   * 稳定排序保证同粒度批的指派可复现（不随容器实现漂移）。
   */
  std::vector<uint32_t>
  PlaceMix (const std::vector<uint32_t> &gs) const
  {
    double a[3], gm[3];
    Coeffs (a, gm);
    const size_t n = gs.size ();
    std::vector<uint32_t> idx (n);
    for (size_t i = 0; i < n; ++i)
      {
        idx[i] = (uint32_t) i;
      }
    // 粒度降序：大任务先落位、小任务填空（LPT 原则）
    std::stable_sort (idx.begin (), idx.end (),
                      [&gs] (uint32_t x, uint32_t y) { return gs[x] > gs[y]; });
    std::vector<uint32_t> loc (n, 0);
    double load[3] = {0.0, 0.0, 0.0}; // 各执行位置当前已承诺的串行负载
    for (size_t k = 0; k < n; ++k)
      {
        uint32_t i = idx[k];
        double bestC = 1e18;
        uint32_t bestP = 0;
        for (uint32_t p = 0; p < 3; ++p)
          {
            double c = load[p] + a[p] * gs[i] + gm[p];
            if (c < bestC - 1e-15)
              {
                bestC = c;
                bestP = p;
              }
        }
        loc[i] = bestP;
        load[bestP] = bestC;
      }
    return loc;
  }

private:
  void
  StartApplication (void) override
  {
    m_socket = Socket::CreateSocket (GetNode (), UdpSocketFactory::GetTypeId ());
    m_socket->Bind (InetSocketAddress (Ipv4Address::GetAny (), m_port));
    m_socket->SetAllowBroadcast (true);
    m_socket->SetRecvCallback (MakeCallback (&OrchestratorApp::HandleRead, this));

    m_start = Simulator::Now ();
    // 受限广播 255.255.255.255 是链路本地的，跨子网不转发，必须用定向广播。
    // 广播地址由 main() 依据 hub 的 LAN 接口直接注入（SetBroadcast），
    // 不能从 m_agents[0]->GetAddress() 反推：终端应用的 m_addr 在其 StartApplication
    // 里才赋值，若编排器先启动则拿到未初始化地址（实测曾得到 102.102.102.255，
    // 使全部查询发往不存在的网段，qryRx 恒为 0）。
    // 串行发起查询：上一轮完成或超时后才发起下一轮，避免并发查询互相污染统计
    // 留 500 ms 让注册与 ARP 收敛，避免首轮查询/任务因邻居未解析而整批失败
    Simulator::Schedule (MilliSeconds (500), &OrchestratorApp::RunOneTask, this, 0u);
  }

  void
  StopApplication (void) override
  {
    if (m_socket)
      {
        m_socket->Close ();
        m_socket = nullptr;
      }
  }

  void
  RunOneTask (uint32_t seq)
  {
    if (seq >= g_cfg.nQueries)
      {
        return;
      }
    m_curSeq = seq;
    m_rspCount[seq] = 0;
    m_dispatched[seq] = false;
    m_expected[seq] = (uint32_t) m_agents.size ();

    if (g_cfg.discovery == "multicast")
      {
        Msg q{MSG_QRY, seq, 0, m_cap, 0, 0, 0};
        std::string s = Encode (q);
        // 单帧定向广播（AP 已桥接，hub 与全部 STA 同处一个 L2 广播域）。
        // ns-3 对非单播帧按 non-unicast（即 ControlMode 指定的基本速率）发送，
        // 与真实 Wi-Fi"多播不做速率自适应"一致，构成命题 1 的物理入口。
        if (m_discStart.find (seq) == m_discStart.end ())
          {
            m_discStart[seq] = Simulator::Now ();
            ++g_rounds;
          }
        m_attempts[seq] = 0;
        SendQuery (seq);
        Simulator::Schedule (MilliSeconds (g_cfg.queryTimeoutMs), &OrchestratorApp::OnQueryTimeout,
                             this, seq);
      }
    else
      {
        // directory / cache：查本地表，零网络往返；cache 命中率 h_hit 在开销上折算
        double overheadS = 0.0;
        if (g_cfg.discovery == "cache")
          {
            overheadS = 0.1 * 0.0; // 命中 90%：仅 10% 需要回查，量级上可忽略
          }
        m_discDone[seq] = Simulator::Now ();
        Simulator::Schedule (Seconds (overheadS), &OrchestratorApp::Dispatch, this, seq);
      }
  }

  void
  SendQuery (uint32_t seq)
  {
    Msg q{MSG_QRY, seq, 0, m_cap, 0, 0, 0};
    std::string s = Encode (q);
    // 单帧定向广播（AP 已桥接，hub 与全部 STA 同处一个 L2 广播域）。
    // ns-3 对非单播帧按 ControlMode 指定的基本速率发送，与真实 Wi-Fi 多播一致。
    Ptr<Packet> p = Create<Packet> ((uint8_t *) s.c_str (), s.size ());
    m_socket->SendTo (p, 0, InetSocketAddress (m_bcast, m_agentPort));
    if (g_cfg.verbose && (seq < 3 || g_querySent % 60 == 0))
      {
        std::cerr << "[QRY-TX] seq=" << seq << " t=" << Simulator::Now ().GetSeconds ()
                  << " bcast=" << m_bcast << " exp=" << m_expected[seq]
                  << " agents=" << m_agents.size () << "\n";
      }
    ++g_querySent;
    g_airtimeUs += (uint64_t) AirtimeFromBytes (s.size (), m_rateBps);
  }

  void
  OnQueryTimeout (uint32_t seq)
  {
    if (m_dispatched[seq])
      {
        return;
      }
    // mDNS 式重发：单次响应可能因 MAC 重传耗尽而永久丢失，重发查询让漏答者补答
    if (got (seq) < m_expected[seq] && m_attempts[seq] < g_cfg.maxRequery)
      {
        ++m_attempts[seq];
        SendQuery (seq);
        Simulator::Schedule (MilliSeconds (g_cfg.queryTimeoutMs), &OrchestratorApp::OnQueryTimeout,
                             this, seq);
        return;
      }
    m_discDone[seq] = Simulator::Now ();
    g_discUs.push_back ((Simulator::Now () - m_discStart[seq]).GetMicroSeconds ());
    g_discMs.push_back ((Simulator::Now () - m_discStart[seq]).GetMilliSeconds ());
    g_missing += (m_expected[seq] - got (seq));
    if (seq < 3)
      {
        std::ostringstream miss;
        for (auto &a : m_agents)
          {
            if (!m_rspIds[seq].count (a->GetAgentId ()))
              {
                miss << a->GetAgentId () << "@" << a->GetAddress () << " ";
              }
          }
        std::cerr << "[DISC] seq=" << seq << " got=" << got (seq) << "/" << m_expected[seq]
                  << " attempts=" << m_attempts[seq] << " missing: " << miss.str () << std::endl;
      }
    Dispatch (seq);
  }

  uint32_t
  got (uint32_t seq) const
  {
    auto it = m_rspIds.find (seq);
    return (it == m_rspIds.end ()) ? 0u : (uint32_t) it->second.size ();
  }

  void
  Dispatch (uint32_t seq)
  {
    if (m_dispatched[seq])
      {
        return;
      }
    // E1 的目的是"发现开销的隔离测量"（02 号文档实验设计第 1 条）。
    // 真实转发改造后任务数据块（g/ρg/C）会真实占用空口与 WAN，
    // 若在 E1 里继续派发任务，发现时滞将被本轮任务流量污染——
    // v3 之前的 E1 数据用解析注入（不占空口）恰好没暴露这个问题。
    // 故 E1 模式只发现、不派发；E2/E4 才有任务面。
    if (g_cfg.mode == "E1")
      {
        m_dispatched[seq] = true;
        // 正常轮次由 FinishOne（任务全部完成/超时）调度下一轮；
        // E1 无任务面，须自行推进轮次，否则 50 轮循环在第 1 轮后停滞。
        Simulator::Schedule (MilliSeconds (g_cfg.queryIntervalMs),
                             &OrchestratorApp::RunOneTask, this, seq + 1);
        return;
      }
    m_dispatched[seq] = true;
    m_dispatchAt[seq] = Simulator::Now ();
    m_pending[seq] = 0;

    uint32_t ctxPerCall =
        (g_cfg.psi == 1) ? (g_cfg.ctxKB * 1024) / g_cfg.m : g_cfg.ctxKB * 1024;

    /* 子任务粒度先整轮采样，再决定放置：
     *  - oracle 策略需要看到整批 m 个粒度才能做 3^m 穷举（批到达排队使放置耦合）；
     *  - mix 策略（批内混排贪心）同样需要整批粒度，但只做 O(m log m) 排序+贪心；
     *  - 其余策略逐个判据放置，采样顺序与旧版一致（不改变既有结果）。
     */
    std::vector<uint32_t> gs (g_cfg.m);
    std::vector<uint32_t> locs (g_cfg.m, 0);
    for (uint32_t j = 0; j < g_cfg.m; ++j)
      {
        gs[j] = SampleG ();
      }
    if (g_cfg.policy == "oracle")
      {
        locs = PlaceOracle (gs);
      }
    else if (g_cfg.policy == "mix")
      {
        locs = PlaceMix (gs);
      }
    else
      {
        for (uint32_t j = 0; j < g_cfg.m; ++j)
          {
            locs[j] = Place (gs[j], g_cfg.policy);
          }
      }

    for (uint32_t j = 0; j < g_cfg.m; ++j)
      {
        uint32_t gBytes = gs[j];
        uint32_t loc = locs[j]; // 执行位置决策 0/1/2

        // 轮转选取持有该能力的智能体承接；智能体均驻留终端，loc 只表示执行宿主位置
        Ptr<AgentNodeApp> target = m_agents[(seq * g_cfg.m + j) % m_agents.size ()];

        // WAN 字节只按最终执行位置计一次
        if (loc == 2)
          {
            g_wanUpBytes += (gBytes + ctxPerCall + g_cfg.hdrB);
            g_wanDnBytes += (uint64_t) (g_cfg.rho * gBytes);
          }

        Msg t{MSG_TASK, seq * 100 + j, target->GetAgentId (), m_cap, loc, gBytes, ctxPerCall};
        std::string s = Encode (t);
        Ptr<Packet> p = Create<Packet> ((uint8_t *) s.c_str (), s.size ());
        ++g_taskSent;
        m_socket->SendTo (p, 0, InetSocketAddress (target->GetAddress (), m_agentPort));
        m_pending[seq]++;
        Simulator::Schedule (MilliSeconds (g_cfg.taskTimeoutMs), &OrchestratorApp::OnTaskTimeout,
                             this, seq, j);
      }
  }

  void
  OnTaskTimeout (uint32_t seq, uint32_t j)
  {
    uint32_t key = seq * 100 + j;
    if (m_taskClosed[key])
      {
        return;
      }
    m_taskClosed[key] = true;
    ++g_taskFailed;
    FinishOne (seq);
  }

  void
  FinishOne (uint32_t seq)
  {
    if (m_pending[seq] > 0 && --m_pending[seq] == 0)
      {
        Simulator::Schedule (MilliSeconds (g_cfg.queryIntervalMs), &OrchestratorApp::RunOneTask, this,
                             seq + 1);
      }
  }

  uint32_t
  SampleG () const
  {
    if (g_cfg.gdist == "lognormal")
      {
        // Box-Muller 生成 N(0,1)，再取指数得到对数正态粒度（H1 假设的松弛）
        double u1 = std::max (1e-9, g_uv->GetValue ());
        double u2 = g_uv->GetValue ();
        double z = std::sqrt (-2.0 * std::log (u1)) * std::cos (2.0 * M_PI * u2);
        double v = std::exp (0.8 * z);
        return (uint32_t) std::max (256.0, g_cfg.g * v);
      }
    return g_cfg.g;
  }

  void
  HandleRead (Ptr<Socket> socket)
  {
    Address from;
    Ptr<Packet> pkt;
    while ((pkt = socket->RecvFrom (from)))
      {
        uint32_t n = pkt->GetSize ();
        std::vector<uint8_t> buf (n + 1, 0);
        pkt->CopyData (buf.data (), n);
        Msg m;
        if (!Decode (std::string ((char *) buf.data ()), m))
          {
            continue;
          }
        if (m.type == MSG_RSP)
          {
            ++g_rspRecv;
            ++g_rspRxByAgent[m.agentId];
            m_rspIds[m.seq].insert (m.agentId); // 去重：重发查询会引来重复应答
            if (got (m.seq) >= m_expected[m.seq] && !m_dispatched[m.seq])
              {
                m_discDone[m.seq] = Simulator::Now ();
                g_discUs.push_back ((Simulator::Now () - m_discStart[m.seq]).GetMicroSeconds ());
                g_discMs.push_back ((Simulator::Now () - m_discStart[m.seq]).GetMilliSeconds ());
                Dispatch (m.seq);
              }
          }
        else if (m.type == MSG_DONE)
          {
            if (m_taskClosed[m.seq])
              {
                continue; // 已超时判失败的迟到响应，丢弃，避免重复计数
              }
            m_taskClosed[m.seq] = true;
            uint32_t seq = m.seq / 100;
            g_latencyMs.push_back ((Simulator::Now () - m_dispatchAt[seq]).GetMilliSeconds ());
            FinishOne (seq);
          }
      }
  }

  uint16_t m_port{60002};
  uint16_t m_agentPort{60000};
  Ipv4Address m_self;
  Ipv4Address m_bcast{"255.255.255.255"};
  double m_rateBps{1e6};
  Ptr<Socket> m_socket;
  std::vector<Ptr<AgentNodeApp>> m_agents;
  std::string m_cap{"cap.sense.temp"};
  uint32_t m_curSeq{0};

  Time m_start;
  std::map<uint32_t, Time> m_discDone;
  std::map<uint32_t, Time> m_discStart;
  std::map<uint32_t, Time> m_dispatchAt;
  std::map<uint32_t, uint32_t> m_rspCount;
  std::map<uint32_t, uint32_t> m_expected;
  std::map<uint32_t, uint32_t> m_pending;
  std::map<uint32_t, bool> m_dispatched;
  std::map<uint32_t, bool> m_taskClosed; // key = seq*100 + j
  std::map<uint32_t, std::set<uint32_t>> m_rspIds;
  std::map<uint32_t, uint32_t> m_attempts;
};
NS_OBJECT_ENSURE_REGISTERED (OrchestratorApp);

/* =======================================================================
 * 输出
 * ======================================================================= */
static void
WriteCsv (const std::string &path, const std::string &header, const std::string &row, bool append)
{
  /* append 仅在目标文件已存在且非空时生效。
   * 原实现直接按调用方的 append 标志打开（seed>1 即 append），在"每个 seed 用独立
   * 文件名"的批量脚本下会让 seed>=2 的文件只有数据行、没有表头——2026-10-21 的
   * E2v2/E3v2/E4/E5 批次因此产生了 80% 无表头文件（数据本身完好）。 */
  bool hasContent = false;
  {
    std::ifstream probe (path, std::ios::binary | std::ios::ate);
    if (probe.good ())
      {
        hasContent = (probe.tellg () > 0);
      }
  }
  bool app = append && hasContent;
  std::ios::openmode m = app ? (std::ios::app) : (std::ios::trunc);
  std::ofstream f (path, m);
  if (!app)
    {
      f << header << "\n";
    }
  f << row << "\n";
}

static double
Quantile (std::vector<double> v, double q)
{
  if (v.empty ())
    {
      return 0.0;
    }
  std::sort (v.begin (), v.end ());
  size_t idx = (size_t) std::floor (q * (v.size () - 1));
  return v[idx];
}

/* =======================================================================
 * main
 * ======================================================================= */
// 关联状态校正（见 main 中调用处说明）：把 AP 侧未到达 GOT_ASSOC_TX_OK 的站点置为已关联
static void
RepairAssoc (Ptr<WifiRemoteStationManager> rsm, NetDeviceContainer stas)
{
  uint32_t fixed = 0;
  for (uint32_t i = 0; i < stas.GetN (); ++i)
    {
      Mac48Address m = Mac48Address::ConvertFrom (stas.Get (i)->GetAddress ());
      if (!rsm->IsAssociated (m))
        {
          rsm->RecordGotAssocTxOk (m);
          ++fixed;
        }
    }
  if (fixed > 0)
    {
      std::cerr << "[ASSOC-FIX] t=" << Simulator::Now ().GetSeconds () << " repaired=" << fixed
                << "\n";
    }
}

int
main (int argc, char *argv[])
{
  CommandLine cmd (__FILE__);
  cmd.AddValue ("mode", "实验块：E1 / E2 / E4", g_cfg.mode);
  cmd.AddValue ("out", "输出目录前缀", g_cfg.out);
  cmd.AddValue ("link", "末梢链路：wifi5 / wifi24 / thread", g_cfg.link);
  cmd.AddValue ("discovery", "发现模式：multicast / directory / cache", g_cfg.discovery);
  cmd.AddValue ("policy", "放置策略：ours / allcloud / alllocal / static / oracle / mix",
                g_cfg.policy);
  cmd.AddValue ("gdist", "粒度分布：fixed / lognormal", g_cfg.gdist);
  cmd.AddValue ("N", "终端智能体数量", g_cfg.N);
  cmd.AddValue ("m", "子任务数", g_cfg.m);
  cmd.AddValue ("g", "子任务粒度（byte）", g_cfg.g);
  cmd.AddValue ("rttMs", "到云 RTT r_c（ms）", g_cfg.rttCloudMs);
  cmd.AddValue ("bwUpMbps", "家庭上行带宽 B_u（Mbps）", g_cfg.bwUpMbps);
  cmd.AddValue ("bwDnMbps", "家庭下行带宽 B_d（Mbps）", g_cfg.bwDnMbps);
  cmd.AddValue ("ctxKB", "基础上下文 C（KB）", g_cfg.ctxKB);
  cmd.AddValue ("psi", "缓存策略 0/1", g_cfg.psi);
  cmd.AddValue ("queryTimeoutMs", "单轮发现等待上限（ms）", g_cfg.queryTimeoutMs);
  cmd.AddValue ("taskTimeoutMs", "单子任务等待上限（ms），超时记失败；大粒度端执行需放宽",
                g_cfg.taskTimeoutMs);
  cmd.AddValue ("respWindowMs", "mDNS 随机应答窗口 W（ms）", g_cfg.respWindowMs);
  cmd.AddValue ("basicMbps", "基本速率（Mbps），折算发现帧空口时长", g_cfg.basicMbps);
  cmd.AddValue ("ctrlMode", "控制/非单播速率，如 OfdmRate6Mbps / OfdmRate24Mbps",
                g_cfg.ctrlMode);
  cmd.AddValue ("bg", "背景负载：none / video / gaming / backup", g_cfg.bg);
  cmd.AddValue ("bgProto", "背景流协议：udp（无反馈 CBR）/ tcp（限速 + NewReno）",
                g_cfg.bgProto);
  cmd.AddValue ("useMeasUp", "ours 也使用网关实测上行（0/1，默认 0=标称）", g_cfg.useMeasUp);
  cmd.AddValue ("bgScale", "背景流强度倍率（默认 1.0）", g_cfg.bgScale);
  cmd.AddValue ("duration", "单次仿真时长（s）", g_cfg.duration);
  cmd.AddValue ("warmupS", "预热时长（s）：仅做关联与 ARP 解析，不测量", g_cfg.warmupS);
  cmd.AddValue ("activeProbe", "终端主动探测 0/1", g_cfg.activeProbe);
  cmd.AddValue ("wifiStd", "Wi-Fi 标准：11a / 11n5 / 11n24", g_cfg.wifiStd);
  cmd.AddValue ("verbose", "打印逐包调试信息 0/1", g_cfg.verbose);
  cmd.AddValue ("pinCw", "钉住竞争窗口（禁用 BEB）0/1", g_cfg.pinCw);
  cmd.AddValue ("seed", "随机种子", g_cfg.seed);
  cmd.Parse (argc, argv);

  // 参数白名单：非法取值必须报错退出，否则会静默落到默认分支产出假数据
  {
    const std::vector<std::string> kDisc{"multicast", "directory", "cache"};
    const std::vector<std::string> kPol{"ours", "allcloud", "alllocal", "static", "oracle",
                                        "mix", "thresh"};
    if (std::find (kDisc.begin (), kDisc.end (), g_cfg.discovery) == kDisc.end ())
      {
        std::cerr << "[FATAL] 未知 discovery: " << g_cfg.discovery
                  << "（可选 multicast/directory/cache）" << std::endl;
        return 3;
      }
    if (std::find (kPol.begin (), kPol.end (), g_cfg.policy) == kPol.end ())
      {
        std::cerr << "[FATAL] 未知 policy: " << g_cfg.policy
                  << "（可选 ours/allcloud/alllocal/static/oracle/mix/thresh）" << std::endl;
        return 3;
      }
  }

  if (g_cfg.link == "thread")
    {
      std::cerr << "[FATAL] --link=thread 暂不可用：ns-3 的 6LoWPAN 只处理 IPv6，IPv4 包会被"
                << " DROP_DISALLOWED_COMPRESSION 丢弃，导致 0 送达。修复方向：Thread 子网改用"
                << " Ipv6AddressHelper，并把 AgentDir/Orchestrator 的套接字改为 IPv6 双栈。"
                << " 在此之前请用 --link=wifi5 或 wifi24。" << std::endl;
      return 2;
    }

  // ARP 加固：默认等待 1 s、重试 4 次、待决队列 3 条，冷启动时易丢首包
  Config::SetDefault ("ns3::ArpCache::WaitReplyTimeout", TimeValue (MilliSeconds (200)));
  Config::SetDefault ("ns3::ArpCache::MaxRetries", UintegerValue (5));

  SeedManager::SetSeed (g_cfg.seed);
  SeedManager::SetRun (g_cfg.seed * 7919); // 保证不同 seed 的流独立
  g_uv = CreateObject<UniformRandomVariable> ();

  // Thread 路径待 IPv6 改造（见前面的 FATAL 分支），当前所有设备一律挂在 Wi-Fi 侧。
  // 否则会创建收不到包的 Thread 节点，把失败率虚高到 30% 量级、污染时延统计。
  uint32_t Nw = g_cfg.N;
  uint32_t Nt = 0;

  NodeContainer nodesCloud, nodesGw, nodesHub, nodesAp, nodesBr;
  nodesCloud.Create (1);
  nodesGw.Create (1);
  nodesHub.Create (1);
  nodesAp.Create (1);
  nodesBr.Create (1);
  NodeContainer nodesSta;
  nodesSta.Create (Nw);
  NodeContainer nodesThread;
  nodesThread.Create (Nt);
  NodeContainer nodesBg;
  nodesBg.Create (1);

  /* ---------- 移动模型（必需）----------
   * YansWifiChannel 的传播损耗模块要取节点的 MobilityModel，缺装会空指针崩溃。
   * 家庭场景为静态拓扑，统一用 ConstantPositionMobilityModel。
   */
  NodeContainer allNodes;
  allNodes.Add (nodesCloud);
  allNodes.Add (nodesGw);
  allNodes.Add (nodesHub);
  allNodes.Add (nodesAp);
  allNodes.Add (nodesBr);
  allNodes.Add (nodesSta);
  allNodes.Add (nodesThread);
  allNodes.Add (nodesBg);
  MobilityHelper mobility;
  mobility.SetMobilityModel ("ns3::ConstantPositionMobilityModel");
  mobility.Install (allNodes);

  /* ---------- 链路层 ---------- */
  PointToPointHelper p2pWan;
  // WAN 速率取 bwUpMbps：改为真实转发后，上下文 C 与结果都要真实占用这条链路，
  // 若仍固定 1 Gbps，则模型里的 B_u（上行带宽）在物理上不存在，E3 的 Λ(B_u) 无从检验。
  // 注：p2p 链路速率对两个方向对称，是"上行受限"的近似（下行走 ρg，通常远小于 C）。
  p2pWan.SetDeviceAttribute ("DataRate",
                             StringValue (std::to_string (g_cfg.bwUpMbps) + "Mbps"));
  p2pWan.SetChannelAttribute ("Delay",
                              StringValue (std::to_string (g_cfg.rttCloudMs / 2.0) + "ms"));
  NetDeviceContainer dWan = p2pWan.Install (NodeContainer (nodesGw.Get (0), nodesCloud.Get (0)));
  // 真实 WAN 字节：gw 侧 MacTx = 上行，cloud 侧 MacTx = 下行
  DynamicCast<PointToPointNetDevice> (dWan.Get (0))
      ->TraceConnectWithoutContext ("MacTx", MakeCallback (&CntWanTx));
  DynamicCast<PointToPointNetDevice> (dWan.Get (1))
      ->TraceConnectWithoutContext ("MacTx", MakeCallback (&CntWanDn));
  // 出口队列探针（网关→云方向）
  {
    Ptr<Queue<Packet>> wq = DynamicCast<PointToPointNetDevice> (dWan.Get (0))->GetQueue ();
    /* 队列深度 1000 包（默认 100）：
     * 应用按任务一次性灌入 g+C 字节（MSS 分段后 64 KB 任务约 68 个包，m=3 并发
     * 即 200 包突发），默认 100 包的缓冲会把这部分**突发**当拥塞丢掉——实测 25%
     * 的任务需要重传，纯属"无拥塞控制 + 瞬时突发"的建模伪影，与真实 CUBIC/QUIC
     * （按 cwnd 平滑发送）不符。放大到 1000 包后丢包只发生在真实过载
     * （如 B_u=10 Mbps 叠加 24 Mbps 上行备份）时才出现，E4 的失效才具有物理意义。 */
    // ns-3.35 的 DropTailQueue 用 "MaxSize"（QueueSize 类型，字符串 "1000p" 表 1000 包）
    wq->SetAttribute ("MaxSize", StringValue ("1000p"));
    wq->TraceConnectWithoutContext ("Enqueue", MakeCallback (&QEnq));
    wq->TraceConnectWithoutContext ("Dequeue", MakeCallback (&QDeq));
  }

  CsmaHelper csmaHome;
  csmaHome.SetChannelAttribute ("DataRate", StringValue ("1Gbps"));
  csmaHome.SetChannelAttribute ("Delay", StringValue ("100ns"));
  NodeContainer homeBus (nodesGw, nodesHub, nodesBg);
  NetDeviceContainer dHome = csmaHome.Install (homeBus);

  WifiHelper wifi;
  // 本树的 wifi 接口为 WifiStandard 枚举（WIFI_STANDARD_*），非旧的 WIFI_PHY_STANDARD_*
  if (g_cfg.wifiStd == "11a")
    {
      wifi.SetStandard (WIFI_STANDARD_80211a);
    }
  else if (g_cfg.wifiStd == "11n24" || g_cfg.link == "wifi24")
    {
      wifi.SetStandard (WIFI_STANDARD_80211n_2_4GHZ);
    }
  else
    {
      wifi.SetStandard (WIFI_STANDARD_80211n_5GHZ);
    }
  // 注意：不能用 Config::SetDefault——RegularWifiMac::ConfigureStandard 会在
  // Install 时用标准默认值覆写 MinCw/MaxCw（实测 SetDefault 后数值与不钉完全一致）。
  // 必须在安装完成后用 Config 路径逐对象设置；MaxCw=MinCw=15 同时封死 BEB 翻倍上限。
  // ConstantRateWifiManager 无 DataRate 属性，用 DataMode/ControlMode。
  // 关键：ControlMode 决定非单播（多播/广播）帧的发送速率 —— 这正是命题 1 的物理入口，
  // 实验中可单独扫描该值以验证"基本速率越低、发现开销越大"。
  // 11a 没有 HT MCS，DataMode 必须换成 OFDM 速率
  std::string dataMode = (g_cfg.wifiStd == "11a") ? "OfdmRate54Mbps" : "HtMcs7";
  wifi.SetRemoteStationManager ("ns3::ConstantRateWifiManager",
                                "DataMode", StringValue (dataMode),
                                "ControlMode", StringValue (g_cfg.ctrlMode));
  YansWifiPhyHelper phy;
  YansWifiChannelHelper chan = YansWifiChannelHelper::Default ();
  phy.SetChannel (chan.Create ());

  WifiMacHelper mac;
  Ssid ssid = Ssid ("home-agents");
  mac.SetType ("ns3::ApWifiMac", "Ssid", SsidValue (ssid));
  NetDeviceContainer dAp = wifi.Install (phy, mac, nodesAp.Get (0));
  mac.SetType ("ns3::StaWifiMac", "Ssid", SsidValue (ssid), "ActiveProbing",
               BooleanValue (g_cfg.activeProbe == 1));
  NetDeviceContainer dSta = wifi.Install (phy, mac, nodesSta);

  // 逐终端 MAC/PHY 层观测（用于定位"应答应了但回程收不到"，见交接文档 5.4-6）
  for (uint32_t i = 0; i < dSta.GetN (); ++i)
    {
      Ptr<WifiNetDevice> wd = DynamicCast<WifiNetDevice> (dSta.Get (i));
      wd->GetMac ()->TraceConnectWithoutContext ("MacTx", MakeBoundCallback (&CntMacTx, i));
      wd->GetMac ()->TraceConnectWithoutContext ("MacTxDrop",
                                                MakeBoundCallback (&CntMacTxDrop, i));
      wd->GetPhy ()->TraceConnectWithoutContext ("PhyTxBegin",
                                                MakeBoundCallback (&CntPhyTxBegin, i));
      wd->GetPhy ()->TraceConnectWithoutContext ("PhyTxDrop",
                                                MakeBoundCallback (&CntPhyTxDrop, i));
      wd->GetPhy ()->TraceConnectWithoutContext ("PhyTxEnd",
                                                MakeBoundCallback (&CntPhyTxEnd, i));
    }
  {
    Ptr<WifiNetDevice> apw = DynamicCast<WifiNetDevice> (dAp.Get (0));
    apw->GetPhy ()->TraceConnectWithoutContext ("PhyTxBegin",
                                                MakeBoundCallback (&CntPhyTxBegin, kApTxId));
    apw->GetPhy ()->TraceConnectWithoutContext ("PhyTxEnd",
                                                MakeBoundCallback (&CntPhyTxEnd, kApTxId));
  }

  if (g_cfg.pinCw == 1)
    {
      const std::string kMacPath = "/NodeList/*/DeviceList/*/$ns3::WifiNetDevice/Mac/"
                                   "$ns3::RegularWifiMac/Txop/$ns3::Txop/";
      Config::Set (kMacPath + "MinCw", UintegerValue (15));
      Config::Set (kMacPath + "MaxCw", UintegerValue (15));
      std::cerr << "[PIN-CW] 已把全部站点的 MinCw/MaxCw 钉在 15（禁用 BEB）\n";
    }

  NetDeviceContainer dThread, dThreadBr;
  if (Nt > 0)
    {
      LrWpanHelper lrw;
      NodeContainer panNodes (nodesBr, nodesThread);
      NetDeviceContainer lrwDev = lrw.Install (panNodes);
      lrw.AssociateToPan (lrwDev, 0x1234);
      SixLowPanHelper six;
      NetDeviceContainer sixDev = six.Install (lrwDev);
      dThreadBr.Add (sixDev.Get (0));
      for (uint32_t i = 1; i < sixDev.GetN (); ++i)
        {
          dThread.Add (sixDev.Get (i));
        }
    }

  /* ---------- 网络层 ---------- */
  // ARP 缓存参数（全局默认，须在安装协议栈之前设置）
  // DeadTimeout 从默认 100 s 收紧到 1 s：真实主机解析失败后会很快重探，
  // 而 ns-3 默认的 100 s 死条目超时会把一次启动期丢包放大成整段仿真失效。
  Config::SetDefault ("ns3::ArpCache::DeadTimeout", TimeValue (Seconds (1)));
  Config::SetDefault ("ns3::ArpCache::AliveTimeout", TimeValue (Seconds (300)));
  Config::SetDefault ("ns3::ArpCache::WaitReplyTimeout", TimeValue (MilliSeconds (100)));
  Config::SetDefault ("ns3::ArpCache::MaxRetries", UintegerValue (8));

  InternetStackHelper stack;
  stack.Install (nodesCloud);
  stack.Install (nodesGw);
  stack.Install (nodesHub);
  stack.Install (nodesAp);
  stack.Install (nodesSta);
  stack.Install (nodesBg);
  if (Nt > 0)
    {
      stack.Install (nodesBr);
      stack.Install (nodesThread);
    }

  // 拓扑：AP 以 CSMA 挂在 hub 上（等价一跳有线回传），再桥接到 Wi-Fi
  NodeContainer bus2 (nodesHub, nodesAp);
  NetDeviceContainer dBus2 = csmaHome.Install (bus2);

  // AP 工作在**桥接**模式（真实家庭 AP 的形态）：把 Wi-Fi 口与以太口桥成同一广播域，
  // 使 hub 与全部 STA 处于同一 L2 网段。这样 mDNS 式广播/多播发现才能直达终端；
  // 若 AP 做三层转发，广播不跨子网，实测 rsp=0（见交接文档 5.4 第 2 条）。
  BridgeHelper bridge;
  NetDeviceContainer apPorts;
  apPorts.Add (dAp.Get (0));   // Wi-Fi 口
  apPorts.Add (dBus2.Get (1)); // 面向 hub 的以太口
  NetDeviceContainer dBridge = bridge.Install (nodesAp.Get (0), apPorts);

  if (Nt > 0)
    {
      NodeContainer bus3 (nodesHub, nodesBr);
      NetDeviceContainer dBus3 = csmaHome.Install (bus3);
      Ipv4AddressHelper a3;
      a3.SetBase ("10.1.30.0", "255.255.255.0");
      a3.Assign (dBus3);
    }

  Ipv4AddressHelper addr;
  addr.SetBase ("10.1.1.0", "255.255.255.0");
  Ipv4InterfaceContainer iWan = addr.Assign (dWan);
  Ipv4Address iCloudAddr = iWan.GetAddress (1);
  addr.SetBase ("10.1.2.0", "255.255.255.0");
  Ipv4InterfaceContainer iHome = addr.Assign (dHome);
  // homeBus 顺序为 (gw, hub, bg)，故 hub 在家庭总线上的地址取索引 1
  Ipv4Address iHubAddr = iHome.GetAddress (1);

  // 桥接后 hub 的以太口与全部 STA 同处 10.1.10.0/24；AP 的桥设备不配 IP（纯二层）
  addr.SetBase ("10.1.10.0", "255.255.255.0");
  Ipv4InterfaceContainer iHubLan = addr.Assign (NetDeviceContainer (dBus2.Get (0)));
  Ipv4InterfaceContainer iSta = addr.Assign (dSta);

  // ---- 预置静态 ARP 表项（排除 ARP 解析失败这一非建模干扰）----
  // 实测依据（交接文档 5.4 第 6 条）：N≥16 时每轮固定 1～2 个终端
  // qryRx=300 / rspTx=300 但 rspRx=0——查询收到了、应答也发出了，回程从未到达目录，
  // 且换种子只是换是哪一个终端。逐终端对账把故障锁定在"终端→hub"的上行单播路径，
  // 首要嫌疑是 ARP 未解析导致应答包在 ArpCache 待发队列里被静默丢弃。
  // 同一广播域内的 ARP 表项在真实网络里也是长期缓存项，不属本文建模对象，故直接预置。
  {
    Ptr<Ipv4L3Protocol> ipHub = nodesHub.Get (0)->GetObject<Ipv4L3Protocol> ();
    uint32_t ifHubLan = ipHub->GetInterfaceForDevice (dBus2.Get (0));
    Ptr<ArpCache> arpHub = ipHub->GetInterface (ifHubLan)->GetArpCache ();
    arpHub->SetAttribute ("AliveTimeout", TimeValue (Seconds (600)));
    arpHub->SetAttribute ("DeadTimeout", TimeValue (Seconds (2)));
    Address hubMac = dBus2.Get (0)->GetAddress ();
    Ipv4Address hubLanIp = iHubLan.GetAddress (0);
    for (uint32_t i = 0; i < dSta.GetN (); ++i)
      {
        Ptr<Ipv4L3Protocol> ip = nodesSta.Get (i)->GetObject<Ipv4L3Protocol> ();
        uint32_t ifIdx = ip->GetInterfaceForDevice (dSta.Get (i));
        Ptr<ArpCache> arp = ip->GetInterface (ifIdx)->GetArpCache ();
        // 说明：本树的 ArpCache::Entry 里 PERMANENT 状态没有对应的 GetTimeout 分支
        // （IsExpired 会落到未定义分支），实测 MarkPermanent 的条目会被后续真实 ARP
        // 解析覆盖回 ALIVE/DEAD，故改用"ALIVE + 长超时"，路径确定且不会被绕过。
        arp->SetAttribute ("AliveTimeout", TimeValue (Seconds (600)));
        arp->SetAttribute ("DeadTimeout", TimeValue (Seconds (2)));
        arp->Add (hubLanIp)->MarkAlive (hubMac);
        g_staArp.push_back (arp);
        arpHub->Add (iSta.GetAddress (i))->MarkAlive (dSta.Get (i)->GetAddress ());
      }
  }

  // AP 侧上行接收计数 + hub 以太口接收计数（判定上行帧是否真的到达 AP/hub）
  DynamicCast<WifiNetDevice> (dAp.Get (0))->GetMac ()->TraceConnectWithoutContext (
      "MacRx", MakeCallback (&CntApRx));
  DynamicCast<WifiNetDevice> (dAp.Get (0))->GetMac ()->TraceConnectWithoutContext (
      "MacRxDrop", MakeCallback (&CntApRxDrop));
  DynamicCast<CsmaNetDevice> (dBus2.Get (0))->TraceConnectWithoutContext (
      "MacRx", MakeCallback (&CntHubEthRx));

  nodesHub.Get (0)->GetObject<Ipv4L3Protocol> ()->TraceConnectWithoutContext (
      "Drop", MakeCallback (&CntHubIp4Drop));

  // IP 层丢包跟踪（逐终端）
  for (uint32_t i = 0; i < nodesSta.GetN (); ++i)
    {
      Ptr<Ipv4L3Protocol> ip = nodesSta.Get (i)->GetObject<Ipv4L3Protocol> ();
      ip->TraceConnectWithoutContext ("Drop", MakeBoundCallback (&CntIp4Drop, i));
      Ptr<ArpL3Protocol> arp = nodesSta.Get (i)->GetObject<ArpL3Protocol> ();
      if (arp)
        {
          arp->TraceConnectWithoutContext ("Drop", MakeBoundCallback (&CntArpDrop, i));
        }
    }
  if (Nt > 0)
    {
      addr.SetBase ("10.1.40.0", "255.255.255.0");
      Ipv4InterfaceContainer iBr = addr.Assign (dThreadBr);
      addr.SetBase ("10.1.41.0", "255.255.255.0");
      addr.Assign (dThread);
    }

  // 网关需三层转发（WAN <-> 家庭总线）；AP 已改为桥接，不再需要 IP 转发。
  // hub 也必须开转发：loc=2 的任务/上下文报文从终端（10.1.10.0/24，经桥接到达 hub）
  // 要跨到 WAN 侧的云（10.1.1.2），这是"真实转发"改造后新出现的路径，
  // 不开则云端子任务全部在 hub 处被静默丢弃。
  nodesGw.Get (0)->GetObject<Ipv4> ()->SetAttribute ("IpForward", BooleanValue (true));
  nodesHub.Get (0)->GetObject<Ipv4> ()->SetAttribute ("IpForward", BooleanValue (true));
  if (Nt > 0)
    {
      nodesBr.Get (0)->GetObject<Ipv4> ()->SetAttribute ("IpForward", BooleanValue (true));
    }

  Ipv4GlobalRoutingHelper::PopulateRoutingTables ();

  /* ---------- 应用层 ----------
   * 端口分配（hub 节点上两个应用必须错开，否则绑定冲突）：
   *   60000  终端智能体接收 QRY/TASK
   *   60001  家庭主机上的能力目录，接收 REG
   *   60002  家庭主机上的编排器，接收 RSP/DONE
   */
  const uint16_t kAgentPort = 60000;
  const uint16_t kDirPort = 60001;
  const uint16_t kOrchPort = 60002;
  // 60003 / 60004 = 执行宿主（hub / cloud），见 kExecHubPort/kExecCloudPort

  Ptr<AgentDirApp> dir = CreateObject<AgentDirApp> ();
  dir->Setup (kDirPort);
  nodesHub.Get (0)->AddApplication (dir);
  dir->SetStartTime (Seconds (0.1));

  // 执行宿主：真实转发落地（loc=1 → hub，loc=2 → cloud）
  Ptr<ExecHostApp> exHub = CreateObject<ExecHostApp> ();
  exHub->Setup (kExecHubPort, g_cfg.f1);
  nodesHub.Get (0)->AddApplication (exHub);
  exHub->SetStartTime (Seconds (0.05));

  Ptr<ExecHostApp> exCloud = CreateObject<ExecHostApp> ();
  exCloud->Setup (kExecCloudPort, g_cfg.f2);
  nodesCloud.Get (0)->AddApplication (exCloud);
  exCloud->SetStartTime (Seconds (0.05));

  /* ---------- E4：背景流量 ----------
   * bg 节点挂在家庭总线上（csmaHome），经网关跨 WAN 与云对打；
   * 上行背景流真实占用 B_u，是"门限漂移"的物理来源。
   */
  Ptr<BgApp> bgUpSnd, bgUpRcv, bgDnSnd, bgDnRcv;
  if (g_cfg.bg != "none")
    {
      Ipv4Address bgAddr = iHome.GetAddress (2); // homeBus 顺序 (gw, hub, bg)
      double upMbps = 0.0, dnMbps = 0.0;
      uint32_t upPkt = 1400, dnPkt = 1400;
      if (g_cfg.bg == "video")
        {
          dnMbps = 20.0;
          upMbps = 0.5;
        }
      else if (g_cfg.bg == "gaming")
        {
          dnMbps = 8.0;
          upMbps = 6.0;
          upPkt = dnPkt = 300;
        }
      else if (g_cfg.bg == "backup")
        {
          // 云备份占 80% 上行（24/30 Mbps）：无丢包、纯带宽争用。
          // 若压到链路容量（≥28 Mbps），尾部丢弃会让整块上下文重组失败、
          // 任务成批超时——那是"丢包型"失效，会掩盖本文要观察的"时延型"门限漂移。
          upMbps = 24.0;
        }
      upMbps *= g_cfg.bgScale;
      dnMbps *= g_cfg.bgScale;
      double t0 = g_cfg.warmupS + 0.5;

      // 网关被动测量：把观测到的背景上行占用从标称上行里扣除（无探针开销）
      g_cfg.bwUpMeasMbps =
          (upMbps > 0.0) ? std::max (0.5, g_cfg.bwUpMbps - upMbps) : g_cfg.bwUpMbps;

      if (g_cfg.bgProto == "tcp")
        {
          /* TCP 背景：OnOff 限速 + TCP（NewReno）接收端。
           * 与 BgApp 的差别：超载时拥塞窗口回退、按公平份额共享，
           * 而非无反馈地持续灌包——§5.7 的 CBR caveat 由此消除。 */
          if (upMbps > 0)
            {
              Ptr<OnOffApplication> s = CreateObject<OnOffApplication> ();
              s->SetAttribute ("Remote",
                               AddressValue (InetSocketAddress (iCloudAddr, kBgUpPort)));
              s->SetAttribute ("DataRate",
                               DataRateValue (DataRate ((uint64_t) (upMbps * 1e6))));
              s->SetAttribute ("PacketSize", UintegerValue (upPkt));
              nodesBg.Get (0)->AddApplication (s);
              s->SetStartTime (Seconds (t0 - 0.01));

              Ptr<PacketSink> r = CreateObject<PacketSink> ();
              r->SetAttribute ("Local",
                               AddressValue (InetSocketAddress (Ipv4Address::GetAny (),
                                                                kBgUpPort)));
              r->SetAttribute ("Protocol", TypeIdValue (TcpSocketFactory::GetTypeId ()));
              nodesCloud.Get (0)->AddApplication (r);
              r->SetStartTime (Seconds (0.05));
            }
          if (dnMbps > 0)
            {
              Ptr<OnOffApplication> s = CreateObject<OnOffApplication> ();
              s->SetAttribute ("Remote",
                               AddressValue (InetSocketAddress (bgAddr, kBgDnPort)));
              s->SetAttribute ("DataRate",
                               DataRateValue (DataRate ((uint64_t) (dnMbps * 1e6))));
              s->SetAttribute ("PacketSize", UintegerValue (dnPkt));
              nodesCloud.Get (0)->AddApplication (s);
              s->SetStartTime (Seconds (t0 - 0.01));

              Ptr<PacketSink> r = CreateObject<PacketSink> ();
              r->SetAttribute ("Local",
                               AddressValue (InetSocketAddress (Ipv4Address::GetAny (),
                                                                kBgDnPort)));
              r->SetAttribute ("Protocol", TypeIdValue (TcpSocketFactory::GetTypeId ()));
              nodesBg.Get (0)->AddApplication (r);
              r->SetStartTime (Seconds (0.05));
            }
        }
      else if (upMbps > 0)
        {
          bgUpSnd = CreateObject<BgApp> ();
          bgUpSnd->Setup (kBgUpPort, iCloudAddr, upMbps, upPkt, true, t0);
          nodesBg.Get (0)->AddApplication (bgUpSnd);
          bgUpSnd->SetStartTime (Seconds (t0 - 0.01));

          bgUpRcv = CreateObject<BgApp> ();
          bgUpRcv->Setup (kBgUpPort, Ipv4Address::GetAny (), 0.0, upPkt, false, t0);
          nodesCloud.Get (0)->AddApplication (bgUpRcv);
          bgUpRcv->SetStartTime (Seconds (0.05));
        }
      if (g_cfg.bgProto != "tcp" && dnMbps > 0)
        {
          bgDnSnd = CreateObject<BgApp> ();
          bgDnSnd->Setup (kBgDnPort, bgAddr, dnMbps, dnPkt, true, t0);
          nodesCloud.Get (0)->AddApplication (bgDnSnd);
          bgDnSnd->SetStartTime (Seconds (t0 - 0.01));

          bgDnRcv = CreateObject<BgApp> ();
          bgDnRcv->Setup (kBgDnPort, Ipv4Address::GetAny (), 0.0, dnPkt, false, t0);
          nodesBg.Get (0)->AddApplication (bgDnRcv);
          bgDnRcv->SetStartTime (Seconds (0.05));
        }
      std::cerr << "[DIAG-BG] proto=" << g_cfg.bgProto << " bg=" << g_cfg.bg
                << " upMbps=" << upMbps << " dnMbps=" << dnMbps
                << " BuMeas=" << g_cfg.bwUpMeasMbps << " t0=" << t0 << "\n";
    }

  std::vector<Ptr<AgentNodeApp>> agents;
  for (uint32_t i = 0; i < Nw; ++i)
    {
      Ptr<AgentNodeApp> a = CreateObject<AgentNodeApp> ();
      // loc 恒为 0：智能体驻留终端；执行宿主位置由编排器决策，见 Execute() 的说明
      a->Setup (i, "cap.sense.temp", 0, iHubAddr, kAgentPort, g_cfg.basicMbps * 1e6);
      a->SetExecHosts (iHubLan.GetAddress (0), iCloudAddr);
      nodesSta.Get (i)->AddApplication (a);
      a->SetStartTime (Seconds (0.2 + 0.05 * i)); // 预热期错峰：每终端一次注册+一次 ARP
      agents.push_back (a);
    }
  for (uint32_t i = 0; i < Nt; ++i)
    {
      Ptr<AgentNodeApp> a = CreateObject<AgentNodeApp> ();
      a->Setup (Nw + i, "cap.sense.temp", 0, iHubAddr, kAgentPort, 250e3);
      a->SetExecHosts (iHubLan.GetAddress (0), iCloudAddr);
      nodesThread.Get (i)->AddApplication (a);
      a->SetStartTime (Seconds (0.2 + 0.05 * i)); // 预热期错峰：每终端一次注册+一次 ARP
      agents.push_back (a);
    }

  Ptr<OrchestratorApp> orch = CreateObject<OrchestratorApp> ();
  orch->Setup (kOrchPort, agents, iHubAddr, g_cfg.basicMbps * 1e6);
  nodesHub.Get (0)->AddApplication (orch);
  // ---- 关联状态校正（预热期内，每 0.5 s 一次）----
  // 本树的 802.11 状态机存在残留：个别站点会停在 WAIT_ASSOC_TX_OK/DISASSOC——
  // 即 AP 发了关联响应但未收到 ACK、重试耗尽后放弃，而终端侧已认为关联成功
  // （linkUp=1、可收广播）。此后 ApWifiMac::Receive 的
  // `!FromDs && ToDs && Addr1==AP && stationManager->IsAssociated(from)` 不成立，
  // 该站点全部上行数据帧被 NotifyRxDrop 丢弃（实测 N=16 时每种子固定 1～2 个站点，
  // 与 seed 无关地贯穿整段仿真）。这是仿真器状态机残留，不是被测机制的性质，
  // 因此在校正窗口内把状态显式置为"已关联"，并把校正次数打印出来，结果中如实报告。
  {
    Ptr<WifiRemoteStationManager> apRsm
        = DynamicCast<WifiNetDevice> (dAp.Get (0))->GetRemoteStationManager ();
    for (double tt = 0.5; tt < g_cfg.warmupS; tt += 0.5)
      {
        Simulator::Schedule (Seconds (tt), &RepairAssoc, apRsm, dSta);
      }
  }

  // 定向广播地址取自 hub 在 10.1.10.0/24 上的地址（AP 桥接后与全部终端同一广播域）
  {
    uint32_t hip = iHubLan.GetAddress (0).Get ();
    orch->SetBroadcast (Ipv4Address ((hip & 0xFFFFFF00u) | 0xFFu));
  }
  // 编排器在预热期结束后才启动；预热期内终端已完成 802.11 关联与 ARP 解析
  orch->SetStartTime (Seconds (g_cfg.warmupS));

  Simulator::Stop (Seconds (g_cfg.duration));
  Simulator::Run ();

  // 执行宿主侧对账：loc=1/2 的任务是否真的到达宿主并被服务
  std::cerr << "[DIAG-HOST] hubTaskRx=" << exHub->TaskRx ()
            << " cloudTaskRx=" << exCloud->TaskRx () << "\n";
  {
    Ptr<PointToPointNetDevice> wanDev = DynamicCast<PointToPointNetDevice> (dWan.Get (0));
    Ptr<Queue<Packet>> q = wanDev->GetQueue ();
    std::cerr << "[DIAG-Q] wanTx: pkts=" << q->GetNPackets () << " bytes=" << q->GetNBytes ()
              << " dequeued=" << g_qN
              << " qDelayMeanMs=" << (g_qN ? g_qDelaySumMs / g_qN : 0.0)
              << " qDelayMaxMs=" << g_qDelayMaxMs
              << " | big: n=" << g_qBigN
              << " mean=" << (g_qBigN ? g_qBigSumMs / g_qBigN : 0.0)
              << " | small: n=" << g_qSmlN
              << " mean=" << (g_qSmlN ? g_qSmlSumMs / g_qSmlN : 0.0) << "\n";
    std::cerr << "[DIAG-QHIST]";
    for (auto &kv : g_qHist)
      {
        std::cerr << " " << (kv.first * 4096) << "B:" << kv.second;
      }
    std::cerr << "\n";
  }
  if (g_cfg.bg != "none")
    {
      std::cerr << "[DIAG-BG] bg=" << g_cfg.bg
                << " upSentB=" << (bgUpSnd ? bgUpSnd->Bytes () : 0)
                << " upRcvB=" << (bgUpRcv ? bgUpRcv->Bytes () : 0)
                << " dnSentB=" << (bgDnSnd ? bgDnSnd->Bytes () : 0)
                << " dnRcvB=" << (bgDnRcv ? bgDnRcv->Bytes () : 0) << "\n";
    }

  /* ---------- 结果落盘 ---------- */
  double p50 = Quantile (g_latencyMs, 0.50);
  double p95 = Quantile (g_latencyMs, 0.95);
  double payload = (double) g_cfg.m * g_cfg.g;
  double lambda = (g_wanUpBytes + g_wanDnBytes) / payload;

  // 真实空口占用与重传总数：命题 1 的直接观测量（airtimeS 是名义折算，见 02 号文档 §4）
  double txBusyUs = g_apTxBusyUs;
  for (uint32_t i = 0; i < g_cfg.N; ++i)
    {
      txBusyUs += g_txBusyUsByAgent.count (i) ? g_txBusyUsByAgent[i] : 0;
    }
  double txBusyS = txBusyUs / 1e6;
  // 重传统计的最终口径（UID 精确）：
  //   retxTotal = Σ(应答帧 PHY 发射次数) − Σ(应答帧应用层发送次数)
  // 演进史（勿回退）：
  //   ① PhyTxBegin−MacTx（AP 帧混入，低 N 时虚高 3 倍）；
  //   ② 仅 STA 侧 PhyTxBegin−MacTx（管理帧 auth/assoc 请求及其重传混入，
  //      实测 N=2 时 MacTx=254 而数据帧仅 ~105，r̄≈2.15 荒谬）；
  //   ③ UID 匹配 staData−staMac（管理帧重传仍混入）；
  //   ④ 应答包 UID 专属计数（本版）：N=2 无碰撞时 r̄→0，机理上唯一自洽。
  uint64_t rspTxAll = 0, rspPhyAll = 0, staData = 0, staOther = 0, staMac = 0, staPhy = 0;
  for (uint32_t i = 0; i < g_cfg.N; ++i)
    {
      rspTxAll += g_rspTxByAgent.count (i) ? g_rspTxByAgent[i] : 0;
      rspPhyAll += g_rspPhyTxByAgent.count (i) ? g_rspPhyTxByAgent[i] : 0;
      staPhy += g_phyTxBeginByAgent.count (i) ? g_phyTxBeginByAgent[i] : 0;
      staMac += g_macTxByAgent.count (i) ? g_macTxByAgent[i] : 0;
      staData += g_phyDataTxByAgent.count (i) ? g_phyDataTxByAgent[i] : 0;
      staOther += g_phyOtherTxByAgent.count (i) ? g_phyOtherTxByAgent[i] : 0;
    }
  uint64_t retxTotal = (rspPhyAll > rspTxAll) ? (rspPhyAll - rspTxAll) : 0;

  std::ostringstream row;
  row << g_cfg.seed << "," << g_cfg.N << "," << g_cfg.m << "," << g_cfg.g << ","
      << g_cfg.rttCloudMs << "," << g_cfg.bwUpMbps << "," << g_cfg.ctxKB << "," << g_cfg.psi << ","
      << g_cfg.discovery << "," << g_cfg.policy << "," << p50 << "," << p95 << ","
      << g_wanUpBytes << "," << g_wanDnBytes << "," << payload << "," << lambda << ","
      << (double) g_airtimeUs / 1e6 << "," << g_taskFailed << "," << g_rounds << ","
      << g_missing << "," << Quantile (g_discMs, 0.50) << "," << Quantile (g_discMs, 0.95) << ","
      << Quantile (g_discUs, 0.50) << "," << Quantile (g_discUs, 0.95) << ","
      << txBusyS << "," << retxTotal << "," << rspTxAll << "," << rspPhyAll << ","
      << g_wanTxRealB << "," << g_wanDnRealB << "," << g_taskSent << "," << g_doneSent;

  WriteCsv (g_cfg.out + ".csv",
            "seed,N,m,g,rttMs,bwUpMbps,ctxKB,psi,discovery,policy,p50,p95,wanUpBytes,wanDnBytes,"
            "payloadBytes,lambda,airtimeS,taskFailed,rounds,missingResp,discP50,discP95,"
            "discP50us,discP95us,txBusyS,retxTotal,rspTxTotal,rspPhyTxTotal,"
            "wanUpRealB,wanDnRealB,taskSent,taskDone",
            row.str (), g_cfg.seed > 1);

  if (g_cfg.verbose)
    {
      std::cerr << "[DIAG-SRC] hub 以太口收帧按源 MAC：\n";
      for (auto &kv : g_hubSrcMac)
        {
          std::cerr << "    " << kv.first << " -> " << kv.second << "\n";
        }
    }
  if (g_cfg.verbose)
    {
      std::cerr << "[DIAG-APDROP] AP 接收丢弃：\n";
      for (auto &kv : g_apRxDrop)
        {
          std::cerr << "    " << kv.first << " -> " << kv.second << "\n";
        }
    }
  std::cerr << "[DIAG-L2] apMacRx=" << g_apMacRx << " hubEthMacRx=" << g_hubEthMacRx << " dirPktRx="
            << g_dirPktRx << " hubIp4Drop=";
  for (auto &kv : g_hubIp4Drop)
    {
      std::cerr << kv.first << ":" << kv.second << " ";
    }
  std::cerr << "\n";
  std::cerr << "[DIAG-RF] txBusyS=" << txBusyS << " retxTotal=" << retxTotal
            << " rspTx=" << rspTxAll << " rspPhyTx=" << rspPhyAll
            << " staPhy=" << staPhy << " staData=" << staData << " staMac=" << staMac
            << " staOther(ACK/BAR等)=" << staOther << "\n";
  std::cerr << "[DIAG] query=" << g_querySent << " rsp=" << g_rspRecv
            << " blkNak=" << g_blkNak << " blkResend=" << g_blkResend
            << " taskSent=" << g_taskSent << " taskRecv=" << g_taskRecv
            << " doneSent=" << g_doneSent << " latencyN=" << g_latencyMs.size () << "\n";

  // 逐终端对账：qryRx=0 说明该终端根本没收到查询（L2 转发/关联问题）；
  // qryRx>0 且 rspTx>0 但 rspRx=0 说明应答在回程被丢；rspTx=0 说明应用层没触发。
  if (g_cfg.N <= 64)
    {
      static const char *kDropName[]
          = {"TTL_EXPIRED", "NO_ROUTE",   "BAD_CHECKSUM", "IFACE_DOWN",
             "LOOPBACK",    "ROUTE_ERROR", "FRAG_TIMEOUT", "INVALID"};
      bool anyAnom = false;
      for (uint32_t id = 0; id < g_cfg.N; ++id)
        {
          uint64_t q = g_qryRxByAgent.count (id) ? g_qryRxByAgent[id] : 0;
          uint64_t rx = g_rspRxByAgent.count (id) ? g_rspRxByAgent[id] : 0;
          if (g_rounds > 0 && (q == 0 || rx < g_rounds))
            {
              anyAnom = true;
            }
        }
      if (anyAnom)
        {
          for (uint32_t id = 0; id < g_cfg.N; ++id)
            {
              uint64_t q = g_qryRxByAgent.count (id) ? g_qryRxByAgent[id] : 0;
              uint64_t tx = g_rspTxByAgent.count (id) ? g_rspTxByAgent[id] : 0;
              uint64_t rx = g_rspRxByAgent.count (id) ? g_rspRxByAgent[id] : 0;
              std::cerr << "[DIAG-AGENT] id=" << id << " qryRx=" << q << " rspTx=" << tx
                        << " rspRx=" << rx << " macTx=" << g_macTxByAgent[id]
                        << " phyTxBegin=" << g_phyTxBeginByAgent[id]
                        << " phyTxDrop=" << g_phyTxDropByAgent[id]
                        << " macTxDrop=" << g_macTxDropByAgent[id];
              if (g_ip4DropByAgent.count (id))
                {
                  std::cerr << " ip4Drop=";
                  for (auto &kv : g_ip4DropByAgent[id])
                    {
                      std::cerr << kDropName[kv.first] << ":" << kv.second << " ";
                    }
                }
              if (g_rspErrByAgent.count (id))
                {
                  std::cerr << " sendErrno=";
                  for (auto &kv : g_rspErrByAgent[id])
                    {
                      std::cerr << kv.first << ":" << kv.second << " ";
                    }
                }
              std::cerr << " arpDrop=" << (g_arpDropByAgent.count (id) ? g_arpDropByAgent[id] : 0);
              if (id < dSta.GetN ())
                {
                  Ptr<ApWifiMac> apm = DynamicCast<ApWifiMac> (
                      DynamicCast<WifiNetDevice> (dAp.Get (0))->GetMac ());
                  if (apm)
                    {
                      Mac48Address want = Mac48Address::ConvertFrom (dSta.Get (id)->GetAddress ());
                      bool found = false;
                      for (auto &kv : apm->GetStaList ())
                        {
                          if (kv.second == want)
                            {
                              found = true;
                            }
                        }
                      std::cerr << " inApList=" << (found ? 1 : 0)
                                << "/" << apm->GetStaList ().size ();
                      Ptr<WifiRemoteStationManager> rsm
                          = DynamicCast<WifiNetDevice> (dAp.Get (0))->GetRemoteStationManager ();
                      if (rsm)
                        {
                          std::cerr << " staAssoc=" << (rsm->IsAssociated (want) ? 1 : 0);
                        }
                    }
                }
              if (id < g_staArp.size () && g_staArp[id])
                {
                  ArpCache::Entry *e = g_staArp[id]->Lookup (iHubLan.GetAddress (0));
                  std::cerr << " arpCachePtr=" << (void *) PeekPointer (g_staArp[id]) << " arpEnt=";
                  if (!e)
                    {
                      std::cerr << "absent";
                    }
                  else
                    {
                      std::cerr << "a" << e->IsAlive () << "p" << e->IsPermanent () << "w"
                                << e->IsWaitReply () << "d" << e->IsDead ();
                    }
                }
              if (g_udpDropByAgent.count (id))
                {
                  std::cerr << " udpDrop(size:n)=";
                  for (auto &kv : g_udpDropByAgent[id])
                    {
                      std::cerr << kv.first << ":" << kv.second << " ";
                    }
                }
              std::cerr << " rounds=" << g_rounds;
              if (id < dSta.GetN ())
                {
                  Ptr<Ipv4L3Protocol> ipx = nodesSta.Get (id)->GetObject<Ipv4L3Protocol> ();
                  int32_t ifx = ipx->GetInterfaceForDevice (dSta.Get (id));
                  bool up = (ifx >= 0) && ipx->GetInterface (ifx)->IsUp ();
                  std::cerr << " linkUp=" << (dSta.Get (id)->IsLinkUp () ? 1 : 0)
                            << " ipv4IfUp=" << (up ? 1 : 0) << " ifIdx=" << ifx;
                }
              std::cerr << ((g_rounds > 0 && (q == 0 || rx < g_rounds)) ? "  <== 异常" : "")
                        << "\n";
            }
        }
    }

  Simulator::Destroy ();
  return 0;
}
