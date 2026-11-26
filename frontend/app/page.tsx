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

const reportPeriods = [
  { value: "weekly", label: "Weekly (last 7 days)" },
  { value: "monthly", label: "Monthly (last 30 days)" },
  { value: "two_months", label: "2 months (last 60 days)" },
  { value: "yearly", label: "Yearly (last 365 days)" },
] as const;

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
  const [editingTicketId, setEditingTicketId] = useState<number | null>(null);
  const [ticketEditName, setTicketEditName] = useState("");
  const [ticketEditPhone, setTicketEditPhone] = useState("");
  const [ticketEditStatus, setTicketEditStatus] = useState("SOLD");
  const [pendingPayments, setPendingPayments] = useState<any[]>([]);
  const [reservations, setReservations] = useState<any[]>([]);
  const [customers, setCustomers] = useState<any[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<any | null>(null);
  const [customerMessages, setCustomerMessages] = useState<any[]>([]);
  const [customerReply, setCustomerReply] = useState("");
  const [customerNotice, setCustomerNotice] = useState("");
  const [showCustomerConversation, setShowCustomerConversation] = useState(false);
  const [activities, setActivities] = useState<any[]>([]);
  const [reports, setReports] = useState<any>({});
  const [reportPeriod, setReportPeriod] =
    useState<(typeof reportPeriods)[number]["value"]>("weekly");
  const [reportError, setReportError] = useState("");
  const [broadcastHistory, setBroadcastHistory] = useState<any[]>([]);
  const [broadcastMessage, setBroadcastMessage] = useState("");
  const [broadcastCustomerIds, setBroadcastCustomerIds] = useState<number[]>([]);
  const [notice, setNotice] = useState("");
  const [paymentPreview, setPaymentPreview] = useState<string | null>(null);
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
      const fifthRound = data.find(
        (lottery: any) => lottery.name?.trim().toLowerCase() === "fifth round",
      );
      setSelectedLottery(fifthRound?.id ?? data[0]?.id ?? null);
    }
  }

  async function loadTickets(lotteryId: number) {
    try {
      const pageSize = 200;
      const firstResponse = await api(
        `/lotteries/${lotteryId}/tickets/manage?page=1&page_size=${pageSize}`,
      );
      if (!firstResponse.ok) {
        setNotice("Could not load ticket details.");
        return;
      }
      const firstPage = await firstResponse.json();
      const pageCount = Number.isInteger(firstPage.pages)
        ? Math.max(1, firstPage.pages)
        : 1;
      const remainingPages = await Promise.all(
        Array.from({ length: pageCount - 1 }, (_, index) =>
          api(`/lotteries/${lotteryId}/tickets/manage?page=${index + 2}&page_size=${pageSize}`),
        ),
      );
      if (remainingPages.some((response) => !response.ok)) {
        setNotice("Could not load all ticket details.");
        return;
      }
      const otherItems = await Promise.all(
        remainingPages.map(async (response) => (await response.json()).items || []),
      );
      setTickets([...(firstPage.items || []), ...otherItems.flat()]);
    } catch (cause) {
      console.error("Could not load ticket details", cause);
      setNotice("Could not reach the server to load ticket details.");
    }
  }

  async function loadProtectedData() {
    await Promise.all([
      api("/admin/overview").then(async (r) => r.ok && setOverview(await r.json())),
      api("/admin/payments/pending").then(async (r) => r.ok && setPendingPayments(await r.json())),
      api("/admin/broadcasts").then(async (r) => r.ok && setBroadcastHistory(await r.json())),
      api("/admin/customers?sort=activity&page_size=100").then(async (r) => {
        if (!r.ok) return;
        const data = await r.json();
        const items = Array.isArray(data.items) ? data.items : [];
        setCustomers(items.sort(
          (left: any, right: any) =>
            Date.parse(right.last_activity_at || right.created_at || "") -
            Date.parse(left.last_activity_at || left.created_at || ""),
        ));
      }),
      api("/admin/activities?page_size=100").then(async (r) => r.ok && setActivities(await r.json())),
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
    else setTickets([]);
  }, [selectedLottery]);

  useEffect(() => {
    if (!authenticated) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await api("/admin/broadcasts");
        if (response.ok) setBroadcastHistory(await response.json());
      } catch (cause) {
        console.error("Could not refresh broadcast history", cause);
      }
    }, 5000);
    return () => window.clearInterval(timer);
  }, [authenticated]);

  useEffect(() => {
    if (!authenticated) return;
    let active = true;
    api(`/admin/reports?period=${reportPeriod}`)
      .then(async (response) => {
        if (!active) return;
        if (response.ok) {
          setReports(await response.json());
          setReportError("");
        } else {
          setReportError("Could not load performance for this period.");
        }
      })
      .catch((cause) => {
        console.error("Could not load performance report", cause);
        if (active) setReportError("Could not reach the server to load this report.");
      });
    return () => {
      active = false;
    };
  }, [authenticated, reportPeriod]);

  useEffect(() => {
    if (!authenticated || !selectedCustomer) return;
    const timer = window.setInterval(async () => {
      await refreshCustomerProfile(selectedCustomer.id);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [authenticated, selectedCustomer?.id]);

  async function refreshCustomerProfile(customerId: number) {
    try {
      const [profileResponse, messagesResponse] = await Promise.all([
        api(`/admin/customers/${customerId}`),
        api(`/admin/customers/${customerId}/messages`),
      ]);
      if (profileResponse.ok) {
        const profile = await profileResponse.json();
        if (profile && typeof profile === "object" && !Array.isArray(profile)) {
          setSelectedCustomer(profile);
        } else {
          setCustomerNotice("The customer profile response was invalid.");
        }
      } else {
        setCustomerNotice("Could not load this customer profile.");
      }
      if (messagesResponse.ok) {
        const messages = await messagesResponse.json();
        if (Array.isArray(messages)) {
          setCustomerMessages(messages.filter(
            (message) => message && typeof message === "object",
          ));
        } else {
          setCustomerMessages([]);
          setCustomerNotice("The customer conversation response was invalid.");
        }
      } else {
        setCustomerMessages([]);
        setCustomerNotice("Could not load this customer's conversation.");
      }
    } catch (cause) {
      console.error("Could not load customer profile and conversation", cause);
      setCustomerNotice("Could not reach the server to load this customer.");
    }
  }

  async function openCustomerProfile(customer: any) {
    setSelectedCustomer(customer);
    setCustomerMessages([]);
    setCustomerNotice("");
    setShowCustomerConversation(false);
    await refreshCustomerProfile(customer.id);
  }

  async function sendCustomerMessage(event: FormEvent) {
    event.preventDefault();
    const message = customerReply.trim();
    if (!selectedCustomer || !message) return;
    let response: Response;
    try {
      response = await api(`/admin/customers/${selectedCustomer.id}/messages`, {
        method: "POST",
        body: JSON.stringify({ message_text: message }),
      });
    } catch (cause) {
      console.error("Could not send customer message", cause);
      setCustomerNotice("Could not reach the server to send this message.");
      return;
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const detail = body?.detail || "Could not send this message.";
      setCustomerNotice(detail);
      return;
    }
    setCustomerReply("");
    setCustomerNotice("Message sent.");
    await refreshCustomerProfile(selectedCustomer.id);
  }

  function closeCustomerProfile() {
    setSelectedCustomer(null);
    setCustomerMessages([]);
    setCustomerNotice("");
    setShowCustomerConversation(false);
  }

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

  function startTicketEdit(ticket: any) {
    setEditingTicketId(ticket.id);
    setTicketEditName(ticket.customer_name || "");
    setTicketEditPhone(ticket.phone_number || "");
    setTicketEditStatus(ticket.status);
    setNotice("");
  }

  async function saveTicketEdit(event: FormEvent, ticket: any) {
    event.preventDefault();
    if (!selectedLottery) return;
    let response: Response;
    try {
      response = await api(
        `/lotteries/${selectedLottery}/tickets/${ticket.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            status: ticketEditStatus,
            full_name: ticketEditStatus === "AVAILABLE" ? null : ticketEditName,
            phone_number: ticketEditStatus === "AVAILABLE" ? null : ticketEditPhone,
          }),
        },
      );
    } catch (cause) {
      console.error("Could not update ticket details", cause);
      setNotice("Could not reach the server to update this number.");
      return;
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const detail = body?.detail;
      const message = Array.isArray(detail)
        ? detail.map((item) => item?.msg).filter(Boolean).join(" ")
        : detail;
      setNotice(typeof message === "string" ? message : "Could not update this number.");
      return;
    }
    setEditingTicketId(null);
    setNotice(`Number ${ticket.number} was updated.`);
    await loadTickets(selectedLottery);
    const [activityResponse, overviewResponse] = await Promise.all([
      api("/admin/activities?page_size=100"),
      api("/admin/overview"),
    ]);
    if (activityResponse.ok) setActivities(await activityResponse.json());
    if (overviewResponse.ok) setOverview(await overviewResponse.json());
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
    if (!broadcastMessage.trim()) {
      setNotice("Enter a message before creating a broadcast.");
      return;
    }
    const audience = broadcastCustomerIds.length
      ? `${broadcastCustomerIds.length} selected customer(s)`
      : "all customers";
    if (!window.confirm(`Send this message to ${audience}?\n\n${broadcastMessage}`)) return;
    const response = await api("/admin/broadcasts", {
      method: "POST",
      body: JSON.stringify({
        message_text: broadcastMessage,
        customer_ids: broadcastCustomerIds.length ? broadcastCustomerIds : undefined,
      }),
    });
    if (response.ok) {
      setBroadcastMessage("");
      setBroadcastCustomerIds([]);
      setNotice("Broadcast queued. Delivery results will update automatically.");
      await loadProtectedData();
    } else {
      setNotice((await response.json()).detail || "Could not queue the broadcast.");
    }
  }

  async function viewPaymentFile(paymentId: number) {
    await showPaymentPreview(`/admin/payments/${paymentId}/attachment`);
  }

  async function viewConversationPaymentImage(attachmentId: number) {
    await showPaymentPreview(
      `/admin/payments/attachments/${attachmentId}`,
      setCustomerNotice,
    );
  }

  async function showPaymentPreview(
    path: string,
    reportError: (message: string) => void = setNotice,
  ) {
    reportError("");
    try {
      const response = await api(path);
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        reportError(body?.detail || `Could not open the payment image (HTTP ${response.status}).`);
        return;
      }
      const blob = await response.blob();
      if (!blob.type.startsWith("image/")) {
        reportError(`The attachment is not an image (${blob.type || "unknown file type"}).`);
        return;
      }
      setPaymentPreview((current) => {
        if (current) URL.revokeObjectURL(current);
        return URL.createObjectURL(blob);
      });
    } catch (cause) {
      console.error("Could not load payment image", cause);
      reportError("Could not reach the server to open this payment image.");
    }
  }

  function closePaymentPreview() {
    setPaymentPreview((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
  }

  function toggleBroadcastCustomer(customerId: number) {
    setBroadcastCustomerIds((current) =>
      current.includes(customerId)
        ? current.filter((id) => id !== customerId)
        : [...current, customerId],
    );
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
        {notice && <p role="status" className="notice">{notice}</p>}

        {activeSection === "Dashboard" && (
          <section className="dashboardSections">
            <section style={cardStyle}>
              <div className="reportHeader">
                <div>
                  <h2>Performance</h2>
                  <p>
                    {reports.period_start && reports.period_end
                      ? `${new Date(reports.period_start).toLocaleDateString()} – ${new Date(reports.period_end).toLocaleDateString()}`
                      : "Choose a period to view performance."}
                  </p>
                </div>
                <label className="reportPeriod">
                  Period
                  <select
                    value={reportPeriod}
                    onChange={(event) =>
                      setReportPeriod(event.target.value as (typeof reportPeriods)[number]["value"])
                    }
                  >
                    {reportPeriods.map((period) => (
                      <option key={period.value} value={period.value}>{period.label}</option>
                    ))}
                  </select>
                </label>
              </div>
              {reportError && <p role="alert" className="error">{reportError}</p>}
              <div className="cards">
                <article className="statCard"><span>Confirmed revenue</span><strong>{reports.confirmed_revenue ?? 0} ETB</strong></article>
                <article className="statCard"><span>Approved payments</span><strong>{reports.approved_payments ?? 0}</strong></article>
                <article className="statCard"><span>Pending payments</span><strong>{reports.pending_payments ?? 0}</strong></article>
                <article className="statCard"><span>Numbers sold</span><strong>{reports.numbers_sold ?? 0}</strong></article>
                <article className="statCard"><span>New customers</span><strong>{reports.new_customers ?? 0}</strong></article>
              </div>
            </section>
            <section style={cardStyle}>
              <h2>Current inventory</h2>
              <div className="cards">
                {[
                  ["Lotteries", overview.total_lotteries],
                  ["Available numbers", overview.available_numbers],
                  ["Reserved numbers", overview.reserved_numbers],
                  ["Sold numbers", overview.sold_numbers],
                ].map(([label, value]) => (
                  <article key={String(label)} className="statCard"><span>{label}</span><strong>{value ?? 0}</strong></article>
                ))}
              </div>
            </section>
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
            <label>
              Lottery
              <select
                value={selectedLottery ?? ""}
                onChange={(event) =>
                  setSelectedLottery(event.target.value ? Number(event.target.value) : null)
                }
              >
                {lotteries.map((lottery) => (
                  <option key={lottery.id} value={lottery.id}>{lottery.name}</option>
                ))}
              </select>
            </label>
            {!selectedLottery ? (
              <p>Create or select a lottery to manage its numbers.</p>
            ) : tickets.length ? (
              <div className="table">
                {tickets.map((ticket) => (
                  <div key={ticket.id}>
                    <div className="ticketRow">
                      <strong>{ticket.number}</strong>
                      <span className={`badge ${ticket.status.toLowerCase()}`}>{ticket.status}</span>
                      {ticket.customer_name || ticket.phone_number ? (
                        <>
                          <span>{ticket.customer_name || "Customer name missing"}</span>
                          <span>{ticket.phone_number || "Phone missing"}</span>
                        </>
                      ) : null}
                      <button className="fileButton" onClick={() => startTicketEdit(ticket)}>
                        Edit number
                      </button>
                    </div>
                    {editingTicketId === ticket.id && (
                      <form
                        onSubmit={(event) => saveTicketEdit(event, ticket)}
                        style={{ display: "grid", gap: 10, padding: "12px 0 18px" }}
                      >
                        <label>
                          Customer name
                          <input
                            value={ticketEditName}
                            onChange={(event) => setTicketEditName(event.target.value)}
                            required={ticketEditStatus === "SOLD"}
                            disabled={ticketEditStatus === "AVAILABLE"}
                          />
                        </label>
                        <label>
                          Phone number
                          <input
                            value={ticketEditPhone}
                            onChange={(event) => setTicketEditPhone(event.target.value)}
                            required={ticketEditStatus === "SOLD"}
                            disabled={ticketEditStatus === "AVAILABLE"}
                          />
                        </label>
                        <label>
                          Number status
                          <select
                            value={ticketEditStatus}
                            onChange={(event) => setTicketEditStatus(event.target.value)}
                            disabled={ticket.status === "RESERVED"}
                          >
                            {ticket.status === "RESERVED" && (
                              <option value="RESERVED">Reserved</option>
                            )}
                            <option value="AVAILABLE">Available</option>
                            <option value="SOLD">Sold</option>
                          </select>
                        </label>
                        {ticket.status === "RESERVED" ? (
                          <p>A reserved number cannot change status until its reservation is resolved.</p>
                        ) : ticketEditStatus === "SOLD" && ticket.status === "AVAILABLE" ? (
                          <p>Saving as sold records a manual sale for the customer details above.</p>
                        ) : null}
                        <div className="actions">
                          <button className="primary" type="submit">Save changes</button>
                          <button type="button" className="fileButton" onClick={() => setEditingTicketId(null)}>
                            Cancel
                          </button>
                        </div>
                      </form>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p>No numbers found for this lottery.</p>
            )}
          </section>
        )}

        {activeSection === "Customers" && (
          <section style={cardStyle}>
            <h2>Customer Directory</h2>
            {customers.map((customer) => (
              <article key={customer.id} className="row">
                <div>
                  <strong>{customer.full_name || "Unnamed customer"}</strong>
                  <div>{customer.phone_number || "No phone"}</div>
                  <time className="customerActivityTime">
                    Last active: {new Date(
                      customer.last_activity_at || customer.created_at,
                    ).toLocaleString()}
                  </time>
                </div>
                <div className="actions">
                  <button className="fileButton" onClick={() => openCustomerProfile(customer)}>
                    View history
                  </button>
                </div>
              </article>
            ))}
          </section>
        )}

        {activeSection === "Reservations" && (
          <section style={cardStyle}>
            <h2>Reservations</h2>
            {reservations.map((reservation) => (
              <article key={reservation.id} className="row"><div><strong>{reservation.customer_name || "Customer"}</strong><div>Numbers: {reservation.numbers.join(", ")}</div></div><span className={`badge ${reservation.status.toLowerCase()}`}>{reservation.status}</span></article>
            ))}
          </section>
        )}

        {activeSection === "Payment Verification" && (
          <section style={cardStyle}>
            <h2>Payment Verification</h2>
            {pendingPayments.map((payment) => (
              <article key={payment.payment_id} className="row">
                <div>
                  <strong>{payment.customer_name}</strong>
                  <div>Numbers: {payment.numbers.join(", ")}</div>
                  <div>{payment.amount} ETB</div>
                  {payment.has_attachment && <button className="fileButton" onClick={() => viewPaymentFile(payment.payment_id)}>View payment image</button>}
                </div>
                <div className="actions"><button className="approve" onClick={() => approvePayment(payment.payment_id)}>Approve</button><button className="reject" onClick={() => rejectPayment(payment.payment_id)}>Reject</button></div>
              </article>
            ))}
            {pendingPayments.length === 0 && <p>No payments awaiting review.</p>}
          </section>
        )}

        {activeSection === "Activities" && (
          <section style={cardStyle}>
            <h2>Customer Activities</h2>
            {activities.map((activity) => (
              <article key={activity.id} className="row">
                <div>
                  <strong>{activity.customer_name || "System activity"}</strong>
                  <div>{activity.phone_number || "No phone number on record"}</div>
                  <div><strong>{activity.activity_type.replaceAll("_", " ")}</strong></div>
                  <div>{activity.description}</div>
                </div>
                <time>{activity.created_at ? new Date(activity.created_at).toLocaleString() : "Date unavailable"}</time>
              </article>
            ))}
            {activities.length === 0 && <p>No customer activities recorded.</p>}
          </section>
        )}

        {activeSection === "Broadcast Messages" && (
          <section style={cardStyle}>
            <h2>Broadcast Messages</h2>
            <textarea value={broadcastMessage} onChange={(e) => setBroadcastMessage(e.target.value)} placeholder="Write a Telegram announcement" className="broadcast" />
            <h3>Recipients ({broadcastCustomerIds.length || "all"})</h3>
            <p>Leave everyone unchecked to send to all known customers.</p>
            <div className="recipientList">
              {customers.map((customer) => (
                <label key={customer.id}>
                  <input
                    type="checkbox"
                    checked={broadcastCustomerIds.includes(customer.id)}
                    onChange={() => toggleBroadcastCustomer(customer.id)}
                  />
                  {customer.full_name || customer.telegram_username || "Unnamed customer"}
                </label>
              ))}
            </div>
            <button className="primary" onClick={createBroadcast}>Create broadcast</button>
            {broadcastHistory.map((item) => (
              <article key={item.id} className="broadcastHistoryItem">
                <div className="broadcastHeading">
                  <strong>{item.status}</strong>
                  <span>Sent {item.sent} · Failed {item.failed} · Pending {item.pending}</span>
                </div>
                <p>{item.message_text}</p>
                {item.failures?.length > 0 && (
                  <details>
                    <summary>Delivery errors ({item.failures.length})</summary>
                    {item.failures.map((failure: any, index: number) => (
                      <p key={`${item.id}-${index}`} className="error">
                        {failure.customer}: {failure.error}
                      </p>
                    ))}
                  </details>
                )}
                {item.failed > 0 && item.status !== "PROCESSING" && (
                  <button
                    className="fileButton"
                    onClick={async () => {
                      if (!window.confirm(`Retry ${item.failed} failed delivery(s)?`)) return;
                      const response = await api(`/admin/broadcasts/${item.id}/retry`, {
                        method: "POST",
                      });
                      if (!response.ok) {
                        const body = await response.json().catch(() => null);
                        setNotice(body?.detail || "Could not retry failed deliveries.");
                        return;
                      }
                      setNotice("Failed deliveries queued for retry.");
                      await loadProtectedData();
                    }}
                  >
                    Retry failed
                  </button>
                )}
              </article>
            ))}
          </section>
        )}

        {activeSection === "Reports" && (
          <section style={cardStyle}>
            <div className="reportHeader">
              <div>
                <h2>Performance</h2>
                <p>
                  {reports.period_start && reports.period_end
                    ? `${new Date(reports.period_start).toLocaleDateString()} – ${new Date(reports.period_end).toLocaleDateString()}`
                    : "Choose a period to view performance."}
                </p>
              </div>
              <label className="reportPeriod">
                Period
                <select
                  value={reportPeriod}
                  onChange={(event) =>
                    setReportPeriod(event.target.value as (typeof reportPeriods)[number]["value"])
                  }
                >
                  {reportPeriods.map((period) => (
                    <option key={period.value} value={period.value}>{period.label}</option>
                  ))}
                </select>
              </label>
            </div>
            {reportError && <p role="alert" className="error">{reportError}</p>}
            <div className="cards">
              <article className="statCard"><span>Confirmed revenue</span><strong>{reports.confirmed_revenue ?? 0} ETB</strong></article>
              <article className="statCard"><span>Approved payments</span><strong>{reports.approved_payments ?? 0}</strong></article>
              <article className="statCard"><span>Pending payments</span><strong>{reports.pending_payments ?? 0}</strong></article>
              <article className="statCard"><span>Numbers sold</span><strong>{reports.numbers_sold ?? 0}</strong></article>
              <article className="statCard"><span>New customers</span><strong>{reports.new_customers ?? 0}</strong></article>
            </div>
            <h3>Current lottery inventory</h3>
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
      {paymentPreview && (
        <div
          className="previewBackdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Payment image"
          onClick={closePaymentPreview}
        >
          <div className="previewDialog" onClick={(event) => event.stopPropagation()}>
            <button className="previewClose" onClick={closePaymentPreview}>Close</button>
            <img src={paymentPreview} alt="Customer payment screenshot" />
          </div>
        </div>
      )}
      {selectedCustomer && (
        <div
          className="profileBackdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Customer history"
          onClick={closeCustomerProfile}
        >
          <section className="profileDialog" onClick={(event) => event.stopPropagation()}>
            <header className="profileHeader">
              <div>
                <h2>{selectedCustomer.full_name || "Unnamed customer"}</h2>
                <p>Phone: {selectedCustomer.phone_number || "Not provided"}</p>
              </div>
              <button className="previewClose" onClick={closeCustomerProfile}>Close</button>
            </header>
            {customerNotice && <p role="status" className="notice">{customerNotice}</p>}
            <section className="customerHistory">
              <h3>Payment and number history</h3>
              {(Array.isArray(selectedCustomer.payments) ? selectedCustomer.payments : []).map((payment: any) => (
                <article className="paymentHistoryItem" key={payment.id}>
                  <div className="paymentHistoryDetails">
                    <span>
                      <strong>Date</strong>
                      {payment.submitted_at || payment.approved_at
                        ? new Date(payment.submitted_at || payment.approved_at).toLocaleString()
                        : "Not available"}
                    </span>
                    <span>
                      <strong>Selected number(s)</strong>
                      {Array.isArray(payment.numbers) && payment.numbers.length
                        ? payment.numbers.join(", ")
                        : "Not available"}
                    </span>
                    <span>
                      <strong>Status</strong>
                      <span className={`badge ${String(payment.status || "").toLowerCase()}`}>
                        {String(payment.status || "UNKNOWN").replaceAll("_", " ")}
                      </span>
                    </span>
                  </div>
                  <div className="paymentHistoryAttachments">
                    {(Array.isArray(payment.attachments) ? payment.attachments : []).map((attachment: any) => (
                      <button
                        className="fileButton"
                        type="button"
                        key={attachment.id}
                        onClick={() => viewConversationPaymentImage(attachment.id)}
                      >
                        View payment image
                      </button>
                    ))}
                    {(!Array.isArray(payment.attachments) || payment.attachments.length === 0) && (
                      <span>No payment image</span>
                    )}
                  </div>
                </article>
              ))}
              {(!Array.isArray(selectedCustomer.payments) || selectedCustomer.payments.length === 0) && (
                <p>No payment history for this customer.</p>
              )}
            </section>
            <details
              className="conversationPanel"
              open={showCustomerConversation}
              onToggle={(event) => setShowCustomerConversation(event.currentTarget.open)}
            >
              <summary>Message customer</summary>
              <section className="profileConversation">
                <p className="conversationHelp">
                  Replies are sent through the bot. The customer must open this bot and press Start first.
                </p>
                <div className="conversationMessages">
                  {customerMessages.filter((message) => !message.attachment_id).map((message) => (
                    <article
                      key={message.id}
                      className={`conversationMessage ${
                        typeof message.direction === "string"
                          ? message.direction.toLowerCase()
                          : "inbound"
                      }`}
                    >
                      <p>{typeof message.message_text === "string" ? message.message_text : ""}</p>
                      <time>{new Date(message.sent_at).toLocaleString()}</time>
                    </article>
                  ))}
                  {customerMessages.every((message) => message.attachment_id) && (
                    <p>No text messages yet.</p>
                  )}
                </div>
                <form className="conversationForm" onSubmit={sendCustomerMessage}>
                  <textarea
                    value={customerReply}
                    onChange={(event) => setCustomerReply(event.target.value)}
                    maxLength={4096}
                    placeholder="Write a message to this customer"
                    required
                  />
                  <button className="primary" type="submit">Send message</button>
                </form>
              </section>
            </details>
          </section>
        </div>
      )}
    </div>
  );
}
