/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * thread-edge.cc —— Thread / IEEE 802.15.4 末梢实测（lr-wpan + 6LoWPAN）
 *
 * 设计文档：家庭网络智能体协同承载边界论文/05_Thread边缘实测方案.md
 * 目的：闭合 SCI 评估"第 1 条硬性缺口"——在 Wi-Fi 之外补上智能家居最具
 *       代表性的承载介质 Thread（802.15.4 + 6LoWPAN）的实测。
 *
 * 两个战役：
 *   T1（已验证）：发现两段律 over 802.15.4 —— leaf 单播查询到 border，测发现时延/成功率随 N 退化。
 *   T2（本次实现）：执行放置 over Thread —— 测 leaf→border 单向时延 τ_lb(g)（含 6LoWPAN 分片）
 *       与 border→cloud 单向时延 τ_bc(g)；放置比较在 analyze_thread_t2.py 中按仿射分解合成
 *       T0=κg/f0t、T1=τ_lb+κg/f1、T2=τ_lb+τ_bc+C/Bu+κg/f1+κg/f2，求 g1* 与 g2*。
 *
 * 关键 ns-3.35 API（已对照 example-ping-lr-wpan.cc 校对）：
 *   安装顺序必须：lrWpanHelper.Install → AssociateToPan → InternetStackHelper.Install
 *                → SixLowPanHelper.Install → Ipv6AddressHelper.Assign
 *   border 双栈：lr-wpan+6LoWPAN(IPv6) + point-to-point(IPv4) 两个网设备，InternetStackHelper 装双栈。
 *
 * 状态：T1 + T2 均已跑通；WSL 迭代修过的坑见 06_Thread实测结果_T1.md §5。
 *
 * 用法：
 *   thread-edge --camp=T1 --N=32 --seed=1 --duration=30 --out=runs/thread/disc
 *   thread-edge --camp=T2 --N=8 --g=16384 --f0thread=1.0 --bwUpMbps=30 --rttCloudMs=30 \
 *               --ctxKB=16 --seed=1 --duration=45 --out=runs/thread/place/x_t2_g16384_f1.0_s1
 */

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/inet-socket-address.h"
#include "ns3/internet-module.h"
#include "ns3/lr-wpan-module.h"
#include "ns3/sixlowpan-module.h"
#include "ns3/mobility-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "ns3/data-rate.h"

#include <fstream>
#include <vector>
#include <string>
#include <cstring>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE ("ThreadEdge");

// ---------- 全局配置 ----------
struct TCfg
{
  std::string camp = "T1";   // T1 = 发现扫描；T2 = 执行放置
  uint32_t N = 32;           // T1: leaf 数；T2: 也用 leaf 数（默认 8）
  uint32_t seed = 1;
  uint32_t pinBe = 0;        // 占位：ns-3.35 LrWpanMac 无退避 setter
  double   duration = 30.0;  // 秒
  double   warmup = 2.0;     // 秒
  uint32_t nQueries = 60;    // T1: 每 leaf 查询数
  double   queryIntervalMs = 100.0;
  uint16_t port = 60020;
  uint32_t querySize = 12;   // T1: CoAP 式轻查询
  double   respWinMs = 10.0;

  // T2 参数
  uint32_t g = 16384;        // 子任务粒度（byte）
  double   f0thread = 1.0;   // Thread leaf 计算力 f0（GFLOP/s）
  double   bwUpMbps = 30.0;  // B_u（推论 2.1(iv)、2.2）
  double   rttCloudMs = 30.0;// r_c
  uint32_t ctxKB = 16;       // C：基础上下文
  double   kappaGflopsPerByte = 0.0043; // κ（与 E2 一致：16KB≈70 GFLOP）
  double   f1 = 2000.0;      // 家庭主机 2 TFLOP/s
  double   f2 = 50000.0;     // 云 50 TFLOP/s
  uint32_t nSends = 6;       // T2: 每发送方发送次数
  double   sendIntervalMs = 1000.0;

  std::string out = "runs/thread/disc";
};

static TCfg g_cfg;

// 共享 CSV（ns-3 单线程，追加安全）
static std::ofstream g_csv;      // T1 发现 / T2 lb
static std::ofstream g_csv_bc;   // T2 bc

// ================= T1：发现 app（leaf 单播查询 / border 应答） =================
class ThreadDiscApp : public Application
{
public:
  static TypeId GetTypeId (void)
  {
    static TypeId tid = TypeId ("ns3::ThreadDiscApp")
      .SetParent<Application> ()
      .SetGroupName ("ThreadEdge")
      .AddConstructor<ThreadDiscApp> ();
    return tid;
  }

  ThreadDiscApp ()
    : m_sock (0), m_role ("leaf"), m_id (0), m_sent (0), m_lastSendT (0),
      m_borderAddr (Ipv6Address::GetAny ()) {}
  virtual ~ThreadDiscApp () {}

  void Setup (Ptr<Node> node, const std::string &role, uint32_t id,
              Ipv6Address borderAddr = Ipv6Address::GetAny ())
  {
    m_node = node; m_role = role; m_id = id; m_borderAddr = borderAddr;
  }

private:
  virtual void StartApplication (void)
  {
    m_sock = Socket::CreateSocket (m_node, UdpSocketFactory::GetTypeId ());
    m_sock->Bind (Inet6SocketAddress (Ipv6Address::GetAny (), g_cfg.port));
    m_sock->SetRecvCallback (MakeCallback (&ThreadDiscApp::HandleRead, this));
    if (m_role == "leaf")
      {
        m_sock->Connect (Inet6SocketAddress (m_borderAddr, g_cfg.port));
        m_sendEvt = Simulator::Schedule (Seconds (g_cfg.warmup),
                                         &ThreadDiscApp::SendQuery, this);
      }
  }

  virtual void StopApplication (void)
  {
    if (m_sock) m_sock->Close ();
  }

  void SendQuery (void)
  {
    if (m_sent >= g_cfg.nQueries) return;
    double t0 = Simulator::Now ().GetSeconds ();
    m_lastSendT = t0;
    int r1 = m_sock->Send (Create<Packet> (g_cfg.querySize));
    std::clog << "DBG T1 leaf " << m_id << " send t=" << t0 << " r=" << r1 << std::endl;
    ++m_sent;
    double jitter = (m_sent * 0.6180339887); jitter -= floor (jitter);
    double delay = g_cfg.queryIntervalMs / 1000.0 + jitter * (g_cfg.respWinMs/1000.0);
    m_sendEvt = Simulator::Schedule (Seconds (delay), &ThreadDiscApp::SendQuery, this);
  }

  void HandleRead (Ptr<Socket> sock)
  {
    Address from;
    Ptr<Packet> p;
    while ((p = sock->RecvFrom (from)))
      {
        double now = Simulator::Now ().GetSeconds ();
        if (m_role == "border")
          {
            std::clog << "DBG T1 border recv t=" << now << std::endl;
            Inet6SocketAddress src = Inet6SocketAddress::ConvertFrom (from);
            int r2 = sock->SendTo (Create<Packet> (g_cfg.querySize), 0, src);
            std::clog << "DBG T1 border reply r=" << r2 << std::endl;
          }
        else
          {
            double rttMs = (now - m_lastSendT) * 1000.0;
            if (g_csv.is_open ())
              g_csv << g_cfg.N << "," << g_cfg.seed << "," << m_id << ","
                    << rttMs << ",1" << std::endl;
          }
      }
  }

  Ptr<Node> m_node;
  Ptr<Socket> m_sock;
  std::string m_role;
  uint32_t m_id;
  uint32_t m_sent;
  double m_lastSendT;
  Ipv6Address m_borderAddr;
  EventId m_sendEvt;
};
NS_OBJECT_ENSURE_REGISTERED (ThreadDiscApp);

// ================= T2：放置 app（leaf→border / border→cloud 单向时延） =================
// 载荷前 8 字节嵌入发送时刻（double），接收方用全局时钟算单向时延（ns-3 单仿真时钟跨节点可比）。
class ThreadPlaceApp : public Application
{
public:
  static TypeId GetTypeId (void)
  {
    static TypeId tid = TypeId ("ns3::ThreadPlaceApp")
      .SetParent<Application> ()
      .SetGroupName ("ThreadEdge")
      .AddConstructor<ThreadPlaceApp> ();
    return tid;
  }

  ThreadPlaceApp () : m_role ("leaf"), m_id (0), m_sent (0),
      m_v6 (0), m_v4 (0), m_borderV6 (Ipv6Address::GetAny ()), m_cloudV4 (Ipv4Address::GetAny ()) {}
  virtual ~ThreadPlaceApp () {}

  void Setup (Ptr<Node> node, const std::string &role, uint32_t id,
              Ipv6Address borderV6 = Ipv6Address::GetAny (),
              Ipv4Address cloudV4 = Ipv4Address::GetAny ())
  {
    m_node = node; m_role = role; m_id = id; m_borderV6 = borderV6; m_cloudV4 = cloudV4;
  }

private:
  virtual void StartApplication (void)
  {
    if (m_role == "leaf")
      {
        // leaf：IPv6 单播到 border（Thread 发现/协作指向 border agent）
        m_v6 = Socket::CreateSocket (m_node, UdpSocketFactory::GetTypeId ());
        m_v6->Bind (Inet6SocketAddress (Ipv6Address::GetAny (), g_cfg.port + 1));
        m_v6->Connect (Inet6SocketAddress (m_borderV6, g_cfg.port + 1));
        m_sendEvt = Simulator::Schedule (Seconds (g_cfg.warmup),
                                         &ThreadPlaceApp::SendProbe, this);
      }
    else if (m_role == "border")
      {
        // border：IPv6 收 leaf 载荷（记 lb 单向时延）+ IPv4 向 cloud 发探针（记 bc 单向时延）
        m_v6 = Socket::CreateSocket (m_node, UdpSocketFactory::GetTypeId ());
        m_v6->Bind (Inet6SocketAddress (Ipv6Address::GetAny (), g_cfg.port + 1));
        m_v6->SetRecvCallback (MakeCallback (&ThreadPlaceApp::RecvV6, this));
        m_v4 = Socket::CreateSocket (m_node, UdpSocketFactory::GetTypeId ());
        m_v4->Bind (InetSocketAddress (Ipv4Address::GetAny (), g_cfg.port + 1));
        m_v4->Connect (InetSocketAddress (m_cloudV4, g_cfg.port + 1));
        m_sendEvt = Simulator::Schedule (Seconds (g_cfg.warmup + 0.5),
                                         &ThreadPlaceApp::SendProbeV4, this);
      }
    else // cloud
      {
        m_v4 = Socket::CreateSocket (m_node, UdpSocketFactory::GetTypeId ());
        m_v4->Bind (InetSocketAddress (Ipv4Address::GetAny (), g_cfg.port + 1));
        m_v4->SetRecvCallback (MakeCallback (&ThreadPlaceApp::RecvV4, this));
      }
  }

  virtual void StopApplication (void)
  {
    if (m_v6) m_v6->Close ();
    if (m_v4) m_v4->Close ();
  }

  Ptr<Packet> MakePayload (void)
  {
    double t0 = Simulator::Now ().GetSeconds ();
    std::vector<uint8_t> buf (g_cfg.g);
    std::memcpy (buf.data (), &t0, sizeof (double));
    return Create<Packet> (buf.data (), g_cfg.g);
  }

  void SendProbe (void)  // leaf → border（IPv6）
  {
    if (m_sent >= g_cfg.nSends) return;
    int r = m_v6->Send (MakePayload ());
    std::clog << "DBG leaf " << m_id << " send t=" << Simulator::Now ().GetSeconds ()
                << " r=" << r << " peer=" << m_borderV6 << std::endl;
    ++m_sent;
    m_sendEvt = Simulator::Schedule (MilliSeconds ((uint32_t) g_cfg.sendIntervalMs),
                                     &ThreadPlaceApp::SendProbe, this);
  }

  void SendProbeV4 (void)  // border → cloud（IPv4）
  {
    if (m_sent >= g_cfg.nSends) return;
    m_v4->Send (MakePayload ());
    ++m_sent;
    m_sendEvt = Simulator::Schedule (MilliSeconds ((uint32_t) g_cfg.sendIntervalMs),
                                     &ThreadPlaceApp::SendProbeV4, this);
  }

  void RecvV6 (Ptr<Socket> sock)  // border 收 leaf → 记 lb 单向时延
  {
    Address from; Ptr<Packet> p;
    while ((p = sock->RecvFrom (from)))
      {
        uint8_t b[8]; p->CopyData (b, 8);
        double t0; std::memcpy (&t0, b, 8);
        double ow = (Simulator::Now ().GetSeconds () - t0) * 1000.0;
        std::clog << "DBG border recvV6 sz=" << p->GetSize () << " ow=" << ow << std::endl;
        if (g_csv.is_open ())
          g_csv << g_cfg.g << "," << g_cfg.seed << "," << m_id << "," << ow << std::endl;
      }
  }

  void RecvV4 (Ptr<Socket> sock)  // cloud 收 border → 记 bc 单向时延
  {
    Address from; Ptr<Packet> p;
    while ((p = sock->RecvFrom (from)))
      {
        uint8_t b[8]; p->CopyData (b, 8);
        double t0; std::memcpy (&t0, b, 8);
        double ow = (Simulator::Now ().GetSeconds () - t0) * 1000.0;
        if (g_csv_bc.is_open ())
          g_csv_bc << g_cfg.g << "," << g_cfg.seed << "," << ow << std::endl;
      }
  }

  Ptr<Node> m_node;
  std::string m_role;
  uint32_t m_id;
  uint32_t m_sent;
  Ptr<Socket> m_v6, m_v4;
  Ipv6Address m_borderV6;
  Ipv4Address m_cloudV4;
  EventId m_sendEvt;
};
NS_OBJECT_ENSURE_REGISTERED (ThreadPlaceApp);

// ================= 拓扑：Thread 星型 PAN + border 双栈 + WAN =================
static void
BuildPan (NodeContainer &border, NodeContainer &leaves, NodeContainer &cloud,
          Ipv6Address &bV6, Ipv4Address &cV4)
{
  border.Create (1); leaves.Create (g_cfg.N); cloud.Create (1);
  NodeContainer pan = border; pan.Add (leaves);

  static MobilityHelper mob;
  mob.SetPositionAllocator ("ns3::GridPositionAllocator",
                           "MinX", DoubleValue (-3.5), "MinY", DoubleValue (-3.5),
                           "DeltaX", DoubleValue (0.5), "DeltaY", DoubleValue (0.5),
                           "GridWidth", UintegerValue (15), "LayoutType", StringValue ("RowFirst"));
  mob.SetMobilityModel ("ns3::ConstantPositionMobilityModel");
  mob.Install (pan);
  mob.Install (cloud);
  border.Get (0)->GetObject<MobilityModel> ()->SetPosition (Vector (0,0,0));

  // Thread 侧：lr-wpan + 6LoWPAN（IPv6）
  // 注意：BuildPan 在 Simulator::Run() 之前就返回，因此本函数内所有 Helper（尤其持有
  // 信道/PHY 的 LrWpanHelper、PointToPointHelper）必须用 static 延长生命周期到程序退出，
  // 否则析构会拆掉 lr-wpan / P2P 链路，PAN 内帧无法投递（border 收不到 leaf 查询），
  // CSV 仅剩表头 1 行。二分验证见 Thread_bisect_报告.md（仅 LrWpanHelper 改 static 即修复）。
  static LrWpanHelper lrw;
  NetDeviceContainer devs = lrw.Install (pan);
  lrw.AssociateToPan (devs, 0x1234);   // border=devs.Get(0) 为 coordinator
  if (getenv ("THREAD_PCAP"))
    lrw.EnablePcap (g_cfg.out + "_lrw", devs, true);
  static InternetStackHelper stack;
  stack.Install (pan);
  static SixLowPanHelper six;
  NetDeviceContainer sixDev = six.Install (devs);
  static Ipv6AddressHelper ipv6;
  ipv6.SetBase (Ipv6Address ("2001:2::"), Ipv6Prefix (64));
  Ipv6InterfaceContainer ifs = ipv6.Assign (sixDev);
  bV6 = ifs.GetAddress (0, 1);         // border 全局 IPv6

  // WAN 侧：border——cloud 点对点（IPv4），带宽=B_u、单向时延=r_c/2
  if (getenv ("THREAD_WAN"))
    {
      static PointToPointHelper p2p;
      p2p.SetDeviceAttribute ("DataRate", DataRateValue (DataRate (std::to_string (g_cfg.bwUpMbps) + "Mbps")));
      p2p.SetChannelAttribute ("Delay", TimeValue (MilliSeconds (g_cfg.rttCloudMs / 2.0)));
      NetDeviceContainer wan = p2p.Install (border.Get (0), cloud.Get (0));
      static InternetStackHelper stack2;          // cloud 装 IPv4 栈
      stack2.Install (cloud);
      static Ipv4AddressHelper ipv4;
      ipv4.SetBase ("10.0.0.0", "255.255.255.0");
      Ipv4InterfaceContainer i4 = ipv4.Assign (wan);
      cV4 = i4.GetAddress (1, 0);          // cloud IPv4
    }

  // 诊断：border 的 IPv6 接口与地址（验证 P2P 接口是否被挂了链路本地地址）
  {
    Ptr<Ipv6> v6 = border.Get (0)->GetObject<Ipv6> ();
    std::clog << "DBG border Ipv6 nIf=" << v6->GetNInterfaces () << std::endl;
    for (uint32_t ii = 0; ii < v6->GetNInterfaces (); ++ii)
      for (uint32_t ai = 0; ai < v6->GetNAddresses (ii); ++ai)
        std::clog << "DBG   if" << ii << " addr=" << v6->GetAddress (ii, ai).GetAddress () << std::endl;
  }
}

// ================= 战役 T1 =================
static void BuildAndRunT1 (void)
{
  NodeContainer border, leaves, cloud;
  Ipv6Address bV6; Ipv4Address cV4;
  BuildPan (border, leaves, cloud, bV6, cV4);

  Ptr<ThreadDiscApp> bApp = CreateObject<ThreadDiscApp> ();
  bApp->Setup (border.Get (0), "border", 0);
  border.Get (0)->AddApplication (bApp);
  bApp->SetStartTime (Seconds (0)); bApp->SetStopTime (Seconds (g_cfg.duration));
  for (uint32_t i = 0; i < g_cfg.N; ++i)
    {
      Ptr<ThreadDiscApp> lApp = CreateObject<ThreadDiscApp> ();
      lApp->Setup (leaves.Get (i), "leaf", i, bV6);
      leaves.Get (i)->AddApplication (lApp);
      lApp->SetStartTime (Seconds (0)); lApp->SetStopTime (Seconds (g_cfg.duration));
    }
  Simulator::Stop (Seconds (g_cfg.duration + 1.0));
  Simulator::Run (); Simulator::Destroy ();
}

// ================= 战役 T2 =================
static void BuildAndRunT2 (void)
{
  NodeContainer border, leaves, cloud;
  Ipv6Address bV6; Ipv4Address cV4;
  BuildPan (border, leaves, cloud, bV6, cV4);

  // leaf 侧：发 g 字节到 border（IPv6）
  for (uint32_t i = 0; i < g_cfg.N; ++i)
    {
      Ptr<ThreadPlaceApp> lApp = CreateObject<ThreadPlaceApp> ();
      lApp->Setup (leaves.Get (i), "leaf", i, bV6, cV4);
      leaves.Get (i)->AddApplication (lApp);
      lApp->SetStartTime (Seconds (0)); lApp->SetStopTime (Seconds (g_cfg.duration));
    }
  // border 侧：收 leaf（记 lb）+ 发 cloud 探针（记 bc）
  Ptr<ThreadPlaceApp> bApp = CreateObject<ThreadPlaceApp> ();
  bApp->Setup (border.Get (0), "border", 0, bV6, cV4);
  border.Get (0)->AddApplication (bApp);
  bApp->SetStartTime (Seconds (0)); bApp->SetStopTime (Seconds (g_cfg.duration));
  // cloud 侧：收 border 探针（记 bc）
  Ptr<ThreadPlaceApp> cApp = CreateObject<ThreadPlaceApp> ();
  cApp->Setup (cloud.Get (0), "cloud", 0, bV6, cV4);
  cloud.Get (0)->AddApplication (cApp);
  cApp->SetStartTime (Seconds (0)); cApp->SetStopTime (Seconds (g_cfg.duration));

  Simulator::Stop (Seconds (g_cfg.duration + 1.0));
  Simulator::Run (); Simulator::Destroy ();
}

int
main (int argc, char *argv[])
{
  CommandLine cmd;
  cmd.AddValue ("camp", "T1=发现扫描 / T2=执行放置", g_cfg.camp);
  cmd.AddValue ("N", "leaf 数", g_cfg.N);
  cmd.AddValue ("seed", "随机种子", g_cfg.seed);
  cmd.AddValue ("pinBe", "占位", g_cfg.pinBe);
  cmd.AddValue ("duration", "时长(秒)", g_cfg.duration);
  cmd.AddValue ("nSends", "T2 每发送方发送次数", g_cfg.nSends);
  cmd.AddValue ("sendIntervalMs", "T2 发送间隔(ms)", g_cfg.sendIntervalMs);
  cmd.AddValue ("g", "T2 子任务粒度(byte)", g_cfg.g);
  cmd.AddValue ("f0thread", "T2 Thread leaf 算力(GFLOP/s)", g_cfg.f0thread);
  cmd.AddValue ("bwUpMbps", "B_u", g_cfg.bwUpMbps);
  cmd.AddValue ("rttCloudMs", "r_c", g_cfg.rttCloudMs);
  cmd.AddValue ("ctxKB", "C", g_cfg.ctxKB);
  cmd.AddValue ("out", "输出 CSV 前缀", g_cfg.out);
  cmd.Parse (argc, argv);

  RngSeedManager::SetSeed (g_cfg.seed);
  if (g_cfg.camp == "T1")
    {
      g_csv.open (g_cfg.out + ".csv");
      g_csv << "N,seed,leafId,discMs,ok" << std::endl;
      BuildAndRunT1 ();
      g_csv.close ();
    }
  else if (g_cfg.camp == "T2")
    {
      g_csv.open (g_cfg.out + "_lb.csv");
      g_csv << "g,seed,leafId,owMs" << std::endl;
      g_csv_bc.open (g_cfg.out + "_bc.csv");
      g_csv_bc << "g,seed,owMs" << std::endl;
      BuildAndRunT2 ();
      g_csv.close (); g_csv_bc.close ();
    }
  else
    {
      NS_FATAL_ERROR ("camp 必须是 T1 或 T2");
    }
  return 0;
}
