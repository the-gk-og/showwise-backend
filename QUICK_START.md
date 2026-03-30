# 🎯 ShowWise Dashboard - Quick Start Guide

## 🚀 Launch in 3 Steps

### 1️⃣ Start the Backend
```bash
cd /home/elijah/Documents/Projects/WEBAPPS/Active-ShowWise/ShowWise-Backend
python app.py
```

### 2️⃣ Open Dashboard
Navigate to: **http://localhost:5001/dashboard**

### 3️⃣ Login
```
Username: admin
Password: Admin@123456
```

---

## 📊 Dashboard Navigation

```
┌─────────────────────────────────────────────────────┐
│            ShowWise Security Dashboard              │
├─────────────────────────────────────────────────────┤
│                                                     │
│  🏠 SIDEBAR              MAIN CONTENT                │
│  ├─ 📊 Overview          ┌──────────────────────┐  │
│  ├─ 🏢 Organizations     │  Real-Time Stats     │  │
│  ├─ 🔒 Security          │  Org │ Users │ ...  │  │
│  ├─ 🌐 IP Management     ├──────────────────────┤  │
│  └─ 📋 Activity & Logs   │  Recent Events       │  │
│                          │  [Event List]        │  │
│                          └──────────────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 🎨 Dashboard Sections

### 1. **📊 Overview**
![Overview Dashboard]
- View all key metrics
- Real-time statistics
- Recent security events
- Quick status check

**Available:**
- Total Organizations
- Total Users
- Security Events Count
- Blocked IPs Count

---

### 2. **🏢 Organizations**
![Organizations Management]
- ➕ Create new organizations
- ✏️ Edit existing organizations
- 🗑️ Delete organizations
- 🔍 Search organizations
- 📋 View organization details

**Quick Action:** Click "New Organization" button

---

### 3. **🔒 Security**
![Security Monitoring]
- 📊 Security KPIs (Critical Events, Failed Logins, High-Risk Requests)
- 🚨 Real-time threat feed
- 🏷️ Filter by event type
- 📌 Filter by severity level
- 📈 Threat trends

**Events Tracked:**
- Failed login attempts
- Blocked requests
- Suspicious activity
- High-risk requests (SQL injection, XSS, etc.)

---

### 4. **🌐 IP Management**
![IP Management]

#### 🚫 Blacklisted IPs (Blocked)
- Permanently blocked addresses
- Shows reason, severity, expiration
- Remove blocked IPs

#### ⚠️ Quarantined IPs (Monitoring)
- IPs under observation
- Threat score displayed
- Can be upgraded to blacklist
- Clear from quarantine

**Action:** Add new IP to blacklist with:
- IP address
- Block reason
- Severity (Low/Medium/High/Critical)
- Duration (in hours)

---

### 5. **📋 Activity & Logs**
![Activity Logs]

**Columns:**
- 🔷 Type (API Request / Security Event)
- 📍 Endpoint / Event
- 📊 Status / Severity
- 🖥️ IP Address
- ⏰ Timestamp

**Features:**
- 🔍 Full-text search
- 🏷️ Filter by type
- 📥 Export as CSV
- 📋 Sortable columns
- ⏱️ Time-based filtering

---

## 🔐 Authentication Flow

```
┌──────────────┐
│  Login Page  │
└──────┬───────┘
       │ Enter credentials
       ▼
┌──────────────────────────────┐
│ POST /api/v1/auth/login      │
│ {username, password}         │
└──────┬───────────────────────┘
       │
       ▼ Verify password
┌──────────────────────────────┐
│ Return access_token          │
│ Store in localStorage        │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────┐
│   Dashboard  │◄─── Use X-API-Key header for all requests
└──────────────┘
```

---

## 🛠️ Common Tasks

### ✅ Create an Organization
1. Click "Organizations" in sidebar
2. Click "➕ New Organization" button
3. Fill in:
   - Organization Name (e.g., "Acme Corp")
   - Slug / URL (e.g., "acme-corp")
4. Click "Save"

### ✅ Monitor Security Events
1. Click "Security" in sidebar
2. View real-time events
3. Use search to filter events
4. Filter by event type
5. Click event for details

### ✅ Block an IP Address
1. Click "IP Management" in sidebar
2. Click "⊕ Add to Blacklist" button
3. Enter:
   - IP Address (e.g., 192.168.1.100)
   - Reason (select from dropdown)
   - Severity (Low/Medium/High/Critical)
   - Duration (in hours)
4. Click "Blacklist"

### ✅ Export Activity Logs
1. Click "Activity & Logs" in sidebar
2. Apply any filters
3. Click "📥 Export CSV" button
4. CSV file downloads automatically
5. Open in Excel/Google Sheets

### ✅ Remove Blocked IP
1. Click "IP Management" in sidebar
2. Find IP in Blacklisted or Quarantined section
3. Click "Remove" or "Clear" button
4. Confirm action

---

## 📱 UI Elements Guide

### 🎛️ Navigation
| Element | Purpose |
|---------|---------|
| Sidebar | Navigate to different sections |
| Top Bar | Shows current page title |
| Breadcrumbs | Show navigation path (if available) |
| Back Button | Return to previous view |

### 🎨 Visual Indicators

**Colors:**
- 🟦 Blue: Primary actions & links
- 🟩 Green: Success & active status
- 🟨 Yellow: Warnings & cautions
- 🟥 Red: Errors & critical alerts

**Badges:**
- `CRITICAL` - Urgent action needed
- `HIGH` - Important alert
- `MEDIUM` - Notable event
- `LOW` - Informational
- `SUCCESS` - Action completed
- `PENDING` - In progress

### 📊 Table Actions
- 🔍 Search within tables
- 🏷️ Filter dropdown selections
- ✏️ Edit button for modifications
- 🗑️ Delete button to remove
- ↔️ Sortable column headers

### 💬 Notifications
- Green alert: ✅ Operation successful
- Red alert: ❌ Error occurred
- Yellow alert: ⚠️ Warning message
- Auto-dismiss: After 5 seconds

---

## 🔌 API Endpoints (for reference)

### Authentication
```
POST /api/v1/auth/login
POST /api/v1/auth/logout
POST /api/v1/auth/verify-2fa
```

### Organizations
```
GET  /api/v1/organizations
POST /api/v1/organizations
GET  /api/v1/organizations/<slug>
PUT  /api/v1/organizations/<slug>
DELETE /api/v1/organizations/<slug>
GET  /api/v1/organizations/<slug>/stats
```

### Security
```
GET  /api/v1/security/dashboard
GET  /api/v1/security/events
GET  /api/v1/security/blocked-ips
GET  /api/v1/security/quarantined-ips
POST /api/v1/security/ip/<ip>/blacklist
POST /api/v1/security/ip/<ip>/quarantine
POST /api/v1/security/ip/<ip>/whitelist
```

### Logs
```
GET  /api/v1/logs/requests
GET  /api/v1/logs/security-events
GET  /api/v1/logs/export/csv
```

### Admin
```
GET  /api/v1/admin/system/stats
GET  /api/v1/admin/system/health
GET  /api/v1/admin/audit/summary
```

---

## 🐛 Troubleshooting

### Dashboard Not Loading
```
✗ Issue: Page won't load
✓ Solution:
  1. Check Flask is running (python app.py)
  2. Verify port 5001 is not in use
  3. Refresh browser (Ctrl+Shift+R)
  4. Check browser console for errors (F12)
```

### API Calls Failing / 401 Errors
```
✗ Issue: "Unauthorized" errors
✓ Solution:
  1. Login again (credentials might have expired)
  2. Token stored in localStorage
  3. Clear browser cache
  4. Try incognito/private window
```

### Can't Login
```
✗ Issue: Login fails
✓ Solution:
  1. Verify credentials (admin / Admin@123456)
  2. Check database is initialized
  3. Ensure Flask server is running
  4. Check /tmp/app.log for errors
```

### Data Not Appearing
```
✗ Issue: "No data" or empty tables
✓ Solution:
  1. Create test data first
  2. Navigate away and back to refresh
  3. Check API is responding
  4. Verify you have proper permissions
```

---

## 📞 Support Information

### Log Files
- **Flask Log:** `/tmp/app.log`
- **Database:** `ShowWise-Backend/showwise.db`
- **Settings:** Check `.env` file for config

### Restart Server
```bash
pkill -f "python app.py"
cd /home/elijah/Documents/Projects/WEBAPPS/Active-ShowWise/ShowWise-Backend
python app.py
```

### View Current Connections
```bash
lsof -i :5001
```

---

## 📈 Performance Tips

1. **Faster Loading:** Clear browser cache regularly
2. **Smoother Experience:** Use modern browser (Chrome, Firefox, Edge)
3. **Better Security:** Keep browser updated
4. **Efficient:** Close unused tabs
5. **Storage:** Regularly export and archive old logs

---

## 🎓 Learning Path

**Beginner:**
1. Login to dashboard
2. View overview statistics
3. Create a test organization
4. Navigate to each section

**Intermediate:**
1. Monitor security events
2. Add IP to blacklist
3. Search and filter logs
4. Export data as CSV

**Advanced:**
1. Use API directly via curl/Postman
2. Integrate with external systems
3. Automate threat responses
4. Create custom reports

---

## 🎯 Key Takeaways

✅ **All-in-One:** Manage organizations, security, IPs, and logs from one place

✅ **Real-Time:** Live event feed and instant updates

✅ **Powerful:** 38+ API endpoints for complete control

✅ **Secure:** Enterprise-grade security with threat detection

✅ **Scalable:** Ready for production deployment

✅ **User-Friendly:** Intuitive interface with no learning curve

---

**🚀 You're all set! Get started now:** http://localhost:5001/dashboard
