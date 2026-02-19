# User Management Guide

The ShowWise Backend includes comprehensive user management capabilities both through the web dashboard and command-line interface.

## Web Dashboard User Management

### Accessing User Management

1. Log in to the admin dashboard
2. Click **Users** in the navigation menu
3. You'll see a list of all users

### Adding a New User

**Via Web Dashboard:**

1. Click **Users** in the navigation
2. Click the **Add User** button
3. Fill in the form:
   - **Username**: Letters, numbers, underscores, and hyphens only
   - **Password**: Minimum 6 characters (12+ recommended)
   - **Confirm Password**: Must match
   - **Role**: Select admin, moderator, or viewer
4. Click **Create User**

### Deleting a User

1. Go to **Users**
2. Find the user in the list
3. Click the **trash icon** button
4. Confirm the deletion

**Note:** You cannot delete:
- The `admin` user (system default)
- Your own account (while logged in)

### Changing Your Password

1. Click **Users** in the navigation
2. Click **Change My Password** button
3. Enter:
   - Current password
   - New password
   - Confirm new password
4. Click **Change Password**

## Command-Line User Management

For Docker containers or headless servers, use the `manage_users.py` CLI tool.

### List All Users

```bash
python manage_users.py list
```

**Output:**
```
======================================================================
  ShowWise Backend Users
======================================================================

Username             Role            Created At               
----------------------------------------------------------------------
admin                admin           2024-02-17T10:30:00     
john_doe             admin           2024-02-17T11:15:00     
----------------------------------------------------------------------
Total users: 2
```

### Add a New User

```bash
python manage_users.py add
```

**Interactive prompts:**
```
======================================================================
  Add New User
======================================================================

Username: new_user
Password: ********
Confirm password: ********
Role [admin]: admin

✓ User 'new_user' created successfully!
```

### Delete a User

```bash
python manage_users.py delete username
```

**Example:**
```bash
python manage_users.py delete john_doe
Are you sure you want to delete user 'john_doe'? (yes/no): yes

✓ User 'john_doe' deleted successfully!
```

### Change a User's Password

```bash
python manage_users.py password username
```

**Example:**
```bash
python manage_users.py password john_doe
New password: ********
Confirm new password: ********

✓ Password changed successfully for user 'john_doe'!
```

### Reset Admin Password

If you're locked out or forgot the admin password:

```bash
python manage_users.py reset-admin
```

**Output:**
```
Reset admin password to 'admin123'? (yes/no): yes

✓ Admin password reset to 'admin123'
⚠  Please change this password immediately after logging in!
```

## Docker Container Usage

If running in a Docker container:

### Interactive Mode

```bash
docker exec -it showwise-backend python manage_users.py list
docker exec -it showwise-backend python manage_users.py add
```

### Non-Interactive Mode (Scripts)

For automation, you can script user creation by piping input:

```bash
echo -e "newuser\npassword123\npassword123\nadmin" | docker exec -i showwise-backend python manage_users.py add
```

## Security Considerations

### Current Implementation

⚠️ **WARNING**: Passwords are currently stored in **plain text** in `data/users.json`. This is suitable for:
- Development environments
- Internal tools
- Trusted networks
- Single-user deployments

### For Production

For production deployments, consider implementing:

1. **Password Hashing**: Use bcrypt or argon2
2. **2FA**: Two-factor authentication
3. **Session Management**: Secure session storage
4. **Audit Logs**: Track user actions
5. **Rate Limiting**: Prevent brute force attacks

### Example: Adding Password Hashing

To add basic password hashing, install bcrypt:

```bash
pip install bcrypt
```

Then modify `app.py`:

```python
import bcrypt

# When creating a user
hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
users[username]['password'] = hashed.decode('utf-8')

# When checking password
if bcrypt.checkpw(password.encode('utf-8'), users[username]['password'].encode('utf-8')):
    # Password is correct
```

## User Roles

Currently implemented roles:

- **admin**: Full access (default)
- **moderator**: Full access (placeholder for future)
- **viewer**: Full access (placeholder for future)

**Note:** Role-based permissions are planned for a future release. Currently all roles have the same permissions.

## Troubleshooting

### "User not found" error

Make sure you're in the correct directory:
```bash
cd /path/to/showwise-backend
ls data/users.json  # Should exist
```

### Permission denied

On Linux/Mac, you may need to make the script executable:
```bash
chmod +x manage_users.py
```

### Cannot delete admin user

The `admin` user is protected and cannot be deleted. This is by design to prevent lockouts.

### Forgot admin password

Use the reset command:
```bash
python manage_users.py reset-admin
```

## Best Practices

1. **Strong Passwords**: Use at least 12 characters with mixed case, numbers, and symbols
2. **Unique Accounts**: Create separate accounts for each admin
3. **Regular Rotation**: Change passwords periodically
4. **Remove Unused**: Delete accounts that are no longer needed
5. **Audit Trail**: Check created_by fields to track who created accounts

## Backup and Recovery

### Backup Users

```bash
cp data/users.json data/users.json.backup
```

### Restore Users

```bash
cp data/users.json.backup data/users.json
```

### Export Users (CSV)

```python
import json
import csv

with open('data/users.json') as f:
    users = json.load(f)

with open('users_export.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow(['Username', 'Role', 'Created At'])
    for username, data in users.items():
        writer.writerow([username, data['role'], data['created_at']])
```

## Future Enhancements

Planned features:

- [ ] Password hashing (bcrypt/argon2)
- [ ] Role-based access control
- [ ] Two-factor authentication
- [ ] User activity logs
- [ ] Password reset via email
- [ ] Account lockout after failed attempts
- [ ] API key management
- [ ] SSO integration (SAML/OAuth)

## Support

For issues with user management:
- Check logs in the terminal where the server is running
- Verify `data/users.json` exists and is valid JSON
- Ensure proper file permissions
- Email: bugs@sfx-crew.com
