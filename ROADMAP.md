# 🗺️ Project Roadmap — Telegram Reminder Bot

This roadmap tracks planned features, improvements, and ideas for the **Telegram Reminder Bot**.

---

## ✅ Current Status
| Area | Status |
|------|---------|
| Core Features | ✅ Complete |
| Timezone Handling | ✅ IST accurate |
| Supabase Integration | ✅ Configured |
| Deployment | ✅ Working on Railway |
| Reminder Precision | ⚠️ Acceptable (within 30s polling) |
| Next Focus | Feature polish & smart UX |

---

## 🧭 Phase 1 — Core Enhancements (Smart & Useful First)
These improve accuracy and reliability without major redesign.

- [ ] ⏱ **Precise scheduling:** Replace 30 s polling with per-reminder timers for second-level accuracy.  
- [ ] 🔔 **Daily summary message:** Send a “Here’s your day” message each morning (configurable time).  
- [ ] ⏰ **Snooze / postpone:** Allow quick replies like “+10 min” or “snooze 1 h” when a reminder fires.  
- [ ] 🗑 **Auto-cleanup:** Automatically delete reminders older than 7 days.  
- [ ] 🗓 **Custom recurring rules:** Support phrases like “every Monday” or “every 3 days”.

---

## 🌍 Phase 2 — Personalization & User Experience
Add customization and polish for each user.

- [ ] 🌏 **User timezones:** Let users set their timezone via `/settimezone`.  
- [ ] 🔐 **User auth:** Optional PIN/token for privacy on shared devices.  
- [ ] 💬 **Personal greetings:** Address users by name (“Good morning, Nithin!”).  
- [ ] 🕹 **Menu shortcuts:** Add `/menu` or custom keyboard for quick actions.  
- [ ] 💡 **Inline buttons:** On reminder, show [✅ Done] [⏰ Snooze 10 min].

---

## 🧠 Phase 3 — Intelligence & Automation
Make the bot understand and adapt better.

- [ ] 🧩 **Smart NLP parsing:** Understand free-form inputs like “remind me before lunch to call dad”.  
- [ ] 🧮 **Natural date phrases:** Parse “next Monday”, “after 2 weeks”, “end of month”.  
- [ ] 🕵️ **Conflict detection:** Warn if two reminders overlap.  
- [ ] 🧠 **AI summaries:** Generate weekly or daily “completed tasks” summaries using LLMs.

---

## ☁️ Phase 4 — Integrations & Ecosystem
Connect reminders with external services.

- [ ] 🗓️ **Google Calendar sync:** Two-way sync between Telegram reminders and Calendar events.  
- [ ] 📨 **Email/SMS notifications:** Alternate delivery channels.  
- [ ] 🧾 **Google Sheets/Notion log:** Log completed reminders automatically.  
- [ ] 💻 **Web dashboard:** Manage reminders visually via React + Supabase.  
- [ ] 🧑‍🤝‍🧑 **Team mode:** Shared reminders for teams with permission control.

---

## 🔧 Phase 5 — Backend & Reliability
Stability, monitoring, and scalability improvements.

- [ ] 🧩 **APScheduler:** Replace manual threading with a robust job scheduler.  
- [ ] 🛠 **Error logging:** Log exceptions and failures into a Supabase table.  
- [ ] 📈 **Analytics dashboard:** Track total reminders, users, and average latency.  
- [ ] ♻️ **Webhook mode:** Switch from polling to Telegram webhooks for faster responses.

---

## 🎯 Phase 6 — Creative Add-Ons
Fun, habit-forming, and quality-of-life features.

- [ ] 🧘 **Focus mode:** Temporarily silence reminders (“focus for 1 hour”).  
- [ ] 🎯 **Gamification/streaks:** Reward users for consistent reminder completion.  
- [ ] 🧾 **Voice input:** Set reminders using voice (speech-to-text).  
- [ ] 🤖 **Smart nightly summary:** Summarize completed tasks and tomorrow’s plan.

---

## 📌 Future Enhancement Log
- [x] **Known Limitation:** Current 30 s polling may trigger reminders up to 30 s late — acceptable for now.  
- [ ] **Future Upgrade:** Implement per-reminder precise scheduling or APScheduler for exact delivery.

---

## 🏁 Roadmap Progress
| Phase | Focus | Progress |
|--------|--------|-----------|
| 1️⃣ | Core Enhancements | 🚧 In progress |
| 2️⃣ | Personalization | ⏳ Planned |
| 3️⃣ | Intelligence & Automation | ⏳ Planned |
| 4️⃣ | Integrations | ⏳ Planned |
| 5️⃣ | Backend & Reliability | ⏳ Planned |
| 6️⃣ | Creative Add-Ons | 💡 Ideas stage |

---

### ✨ Notes
This roadmap is living documentation — update it as milestones are reached.  
Feature ideas or bugs can be tracked as **GitHub Issues** linked from this file.

---

_Updated Oct 2025_
