"use client";

import { FormEvent, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const navigation = [
  "Dashboard",
  "Lotteries",
  "Number Management",
  "Customers",
  "Reservations",
  "Payment Verification",
  "Activities",
  "Broadcast Messages",
  "Reports",
  "Settings",
] as const;

type Section = (typeof navigation)[number];

export default function AdminPage() {
  const [authenticated, setAuthenticated] = useState(false);
  const [activeSection, setActiveSection] = useState<Section>("Dashboard");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [overview, setOverview] = useState<Record<string, number>>({});
  const [lotteries, setLotteries] = useState<any[]>([]);
  const [selectedLottery, setSelectedLottery] = useState<number | null>(null);
  const [tickets, setTickets] = useState<any[]>([]);
  const [ticketStatus, setTicketStatus] = useState("");
  const [ticketSearch, setTicketSearch] = useState("");
  const [pendingPayments, setPendingPayments] = useState<any[]>([]);
  const [reservations, setReservations] = useState<any[]>([]);
  const [customers, setCustomers] = useState<any[]>([]);
  const [activities, setActivities] = useState<any[]>([]);
  const [reports, setReports] = useState<any>({});
  const [broadcastHistory, setBroadcastHistory] = useState<any[]>([]);
  const [broadcastMessage, setBroadcastMessage] = useState("");
  const [lotteryName, setLotteryName] = useState("");
  const [startNumber, setStartNumber] = useState("000");
  const [endNumber, setEndNumber] = useState("999");
  const [ticketPrice, setTicketPrice] = useState("100");
  const [duration, setDuration] = useState("24");
  const [customerLimit, setCustomerLimit] = useState("100");

  async function api(path: string, options: RequestInit = {}) {
    return fetch(`${API_URL}${path}`, {
      ...options,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
  }

  async function loadLotteries() {
    const response = await api("/lotteries");
    if (response.ok) {
      const data = await response.json();
      setLotteries(data);
      if (!selectedLottery && data.length) setSelectedLottery(data[0].id);
    }
  }

  async function loadTickets(lotteryId: number, status = ticketStatus, search = ticketSearch) {
    const params = new URLSearchParams({ page: "1", page_size: "100" });
    if (status) params.set("status", status);
    if (search) params.set("search", search);
    const response = await api(`/lotteries/${lotteryId}/tickets?${params}`);
    if (response.ok) setTickets((await response.json()).items || []);
  }

  async function loadProtectedData() {
    await Promise.all([
      api("/admin/overview").then(async (r) => r.ok && setOverview(await r.json())),
      api("/admin/payments/pending").then(async (r) => r.ok && setPendingPayments(await r.json())),
      api("/admin/broadcasts").then(async (r) => r.ok && setBroadcastHistory(await r.json())),
      api("/admin/customers?page_size=100").then(async (r) => r.ok && setCustomers((await r.json()).items || [])),
      api("/admin/activities?page_size=100").then(async (r) => r.ok && setActivities(await r.json())),
      api("/admin/reports").then(async (r) => r.ok && setReports(await r.json())),
      api("/reservations/admin/list").then(async (r) => r.ok && setReservations(await r.json())),
    ]);
    await loadLotteries();
  }

  useEffect(() => {
    api("/admin/me")
      .then(async (response) => {
        setAuthenticated(response.ok);
        if (response.ok) await loadProtectedData();
      })
      .catch(() => setAuthenticated(false));
  }, []);

  useEffect(() => {
    if (selectedLottery) loadTickets(selectedLottery);
  }, [selectedLottery, ticketStatus, ticketSearch]);

  async function login(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await api("/admin/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      setError((await response.json()).detail || "Login failed");
      return;
    }
    setAuthenticated(true);
    await loadProtectedData();
  }

  async function logout() {
    await api("/admin/logout", { method: "POST", body: "{}" });
    setAuthenticated(false);
  }

  async function createLottery(event: FormEvent) {
    event.preventDefault();
    setError("");
    const start = Number(startNumber);
    const end = Number(endNumber);
    if (!Number.isInteger(start) || !Number.isInteger(end) || end < start) {
      setError("Enter a valid starting and ending number.");
      return;
    }
    const response = await api("/lotteries", {
      method: "POST",
      body: JSON.stringify({
        name: lotteryName,
        start_number: start,
        end_number: end,
        ticket_price: ticketPrice,
        currency: "ETB",
        reservation_duration_hours: Number(duration),
        max_numbers_per_customer: Number(customerLimit),
        status: "ACTIVE",
      }),
    });
    if (!response.ok) {
      setError((await response.json()).detail || "Could not create lottery");
      return;
    }
    setLotteryName("");
    await loadProtectedData();
  }

  async function updateLotteryStatus(lotteryId: number, status: string) {
    const response = await api(`/lotteries/${lotteryId}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    if (response.ok) await loadProtectedData();
  }

  async function approvePayment(paymentId: number) {
    if (!window.confirm("Approve this payment and confirm the reserved numbers?")) return;
    const response = await api(`/admin/payments/${paymentId}/approve`, {
      method: "POST",
      body: JSON.stringify({ allow_expired_explicit: false }),
    });
    if (!response.ok) window.alert((await response.json()).detail || "Payment approval failed");
    await loadProtectedData();
  }

  async function rejectPayment(paymentId: number) {
    const reason = window.prompt("Enter a rejection reason:");
    if (!reason?.trim()) return;
    if (!window.confirm("Reject this payment and release its reserved numbers?")) return;
    const response = await api(`/admin/payments/${paymentId}/reject`, {
      method: "POST",
      body: JSON.stringify({ rejection_reason: reason.trim() }),
    });
    if (!response.ok) window.alert((await response.json()).detail || "Payment rejection failed");
    await loadProtectedData();
  }

  async function createBroadcast() {
    if (!broadcastMessage.trim()) return;
    const response = await api("/admin/broadcasts", {
      method: "POST",
      body: JSON.stringify({ message_text: broadcastMessage }),
    });
    if (response.ok) {
      setBroadcastMessage("");
      await loadProtectedData();
    }
  }

  if (!authenticated) {
    return (
      <main className="loginPage">
        <form onSubmit={login} className="loginCard">
          <h1>DawitAppachMotor</h1>
          <p>Private administrator login</p>
          {error && <p className="error">{error}</p>}
          <label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} required /></label>
          <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} /></label>
          <button type="submit" className="primary">Sign in</button>
        </form>
      </main>
    );
  }

  const cardStyle: React.CSSProperties = { background: "white", borderRadius: 10, padding: 20 };

  return (
    <div className="layout">
      <aside className="sidebar">
        <h2>DawitAppachMotor</h2>
        <nav>
          {navigation.map((item) => (
            <button key={item} className={activeSection === item ? "navActive" : ""} onClick={() => setActiveSection(item)}>
              {item}
            </button>
          ))}
        </nav>
        <button className="logout" onClick={logout}>Logout</button>
      </aside>

      <main className="content">
        <h1>{activeSection}</h1>

        {activeSection === "Dashboard" && (
          <section className="cards">
            {[
              ["Lotteries", overview.total_lotteries],
              ["Available", overview.available_numbers],
              ["Reserved", overview.reserved_numbers],
              ["Sold", overview.sold_numbers],
              ["Pending payments", overview.pending_payments],
              ["Approved revenue", `${overview.approved_revenue ?? 0} ETB`],
            ].map(([label, value]) => (
              <article key={String(label)} className="statCard"><span>{label}</span><strong>{value ?? 0}</strong></article>
            ))}
          </section>
        )}

        {activeSection === "Lotteries" && (
          <section style={{ display: "grid", gap: 16 }}>
            {error && <p className="error">{error}</p>}
            <form onSubmit={createLottery} style={cardStyle} className="lotteryForm">
              <h2>Create lottery</h2>
              <label>Name<input value={lotteryName} onChange={(e) => setLotteryName(e.target.value)} required /></label>
              <label>Starting number<input value={startNumber} onChange={(e) => setStartNumber(e.target.value)} required /></label>
              <label>Ending number<input value={endNumber} onChange={(e) => setEndNumber(e.target.value)} required /></label>
              <label>Ticket price (ETB)<input type="number" min="0" step="0.01" value={ticketPrice} onChange={(e) => setTicketPrice(e.target.value)} required /></label>
              <label>Reservation duration (hours)<input type="number" min="1" value={duration} onChange={(e) => setDuration(e.target.value)} required /></label>
              <label>Maximum numbers/customer<input type="number" min="1" value={customerLimit} onChange={(e) => setCustomerLimit(e.target.value)} required /></label>
              <button type="submit" className="primary">Create lottery</button>
            </form>
            <div style={cardStyle}>
              <h2>Lotteries</h2>
              {lotteries.length === 0 ? <p>No lotteries created.</p> : lotteries.map((lottery) => (
                <article key={lottery.id} className="row">
                  <div><strong>{lottery.name}</strong><div>{lottery.start_number} - {lottery.end_number} · {lottery.ticket_price} ETB · {lottery.status}</div></div>
                  <select value={lottery.status} onChange={(e) => updateLotteryStatus(lottery.id, e.target.value)}>
                    <option>DRAFT</option><option>ACTIVE</option><option>PAUSED</option><option>CLOSED</option>
                  </select>
                </article>
              ))}
            </div>
          </section>
        )}

        {activeSection === "Number Management" && (
          <section style={cardStyle}>
            <h2>Number Management</h2>
            <div className="filters">
              <select value={selectedLottery || ""} onChange={(e) => setSelectedLottery(Number(e.target.value))}>
                {lotteries.map((lottery) => <option key={lottery.id} value={lottery.id}>{lottery.name}</option>)}
              </select>
              <select value={ticketStatus} onChange={(e) => setTicketStatus(e.target.value)}>
                <option value="">All statuses</option><option>AVAILABLE</option><option>RESERVED</option><option>SOLD</option>
              </select>
              <input placeholder="Search number" value={ticketSearch} onChange={(e) => setTicketSearch(e.target.value)} />
            </div>
            <div className="table">
              {tickets.map((ticket) => <div className="ticketRow" key={ticket.id}><strong>{ticket.number}</strong><span className={`badge ${ticket.status.toLowerCase()}`}>{ticket.status}</span></div>)}
            </div>
          </section>
        )}

        {activeSection === "Customers" && (
          <section style={cardStyle}>
            <h2>Customer Directory</h2>
            {customers.map((customer) => (
              <article key={customer.id} className="row"><div><strong>{customer.full_name || "Unnamed customer"}</strong><div>{customer.phone_number} · Telegram {customer.telegram_id}</div></div><span>{customer.purchased_numbers} purchased</span></article>
            ))}
          </section>
        )}

        {activeSection === "Reservations" && (
          <section style={cardStyle}>
            <h2>Reservations</h2>
            {reservations.map((reservation) => (
              <article key={reservation.id} className="row"><div><strong>{reservation.reference}</strong><div>{reservation.customer_name} · {reservation.numbers.join(", ")}</div></div><span className={`badge ${reservation.status.toLowerCase()}`}>{reservation.status}</span></article>
            ))}
          </section>
        )}

        {activeSection === "Payment Verification" && (
          <section style={cardStyle}>
            <h2>Payment Verification</h2>
            {pendingPayments.map((payment) => (
              <article key={payment.payment_id} className="row">
                <div><strong>{payment.customer_name}</strong><div>{payment.reservation_reference} · {payment.numbers.join(", ")}</div><div>{payment.amount} ETB</div>{payment.has_attachment && <a href={`${API_URL}/admin/payments/${payment.payment_id}/attachment`} target="_blank">View screenshot</a>}</div>
                <div className="actions"><button className="approve" onClick={() => approvePayment(payment.payment_id)}>Approve</button><button className="reject" onClick={() => rejectPayment(payment.payment_id)}>Reject</button></div>
              </article>
            ))}
            {pendingPayments.length === 0 && <p>No payments awaiting review.</p>}
          </section>
        )}

        {activeSection === "Activities" && (
          <section style={cardStyle}>
            <h2>Customer Activities</h2>
            {activities.map((activity) => <article key={activity.id} className="row"><div><strong>{activity.activity_type}</strong><div>{activity.description}</div></div><span>{activity.created_at}</span></article>)}
          </section>
        )}

        {activeSection === "Broadcast Messages" && (
          <section style={cardStyle}>
            <h2>Broadcast Messages</h2>
            <textarea value={broadcastMessage} onChange={(e) => setBroadcastMessage(e.target.value)} placeholder="Write a Telegram announcement" className="broadcast" />
            <button className="primary" onClick={createBroadcast}>Create broadcast</button>
            {broadcastHistory.map((item) => <article key={item.id} className="row"><div><strong>{item.status}</strong><div>{item.message_text}</div></div><span>Sent {item.sent} · Failed {item.failed}</span></article>)}
          </section>
        )}

        {activeSection === "Reports" && (
          <section style={cardStyle}>
            <h2>Sales Reports</h2>
            <div className="cards">
              <article className="statCard"><span>Confirmed revenue</span><strong>{reports.confirmed_revenue ?? 0} ETB</strong></article>
              <article className="statCard"><span>Approved payments</span><strong>{reports.approved_payments ?? 0}</strong></article>
              <article className="statCard"><span>Pending payments</span><strong>{reports.pending_payments ?? 0}</strong></article>
            </div>
            {(reports.lotteries || []).map((lottery: any) => <article key={lottery.lottery_id} className="row"><strong>{lottery.name}</strong><span>Available {lottery.available} · Reserved {lottery.reserved} · Sold {lottery.sold}</span></article>)}
          </section>
        )}

        {activeSection === "Settings" && (
          <section style={cardStyle}>
            <h2>Settings</h2>
            <p>Configure lottery details in the <strong>Lotteries</strong> section. Environment and payment settings require the deployment configuration and API settings implementation.</p>
          </section>
        )}
      </main>
    </div>
  );
}
