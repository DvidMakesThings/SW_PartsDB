# Django Admin Credentials Guide

## Creating a Superuser (Admin Account)

To access the Django admin interface at `http://localhost:8000/admin/`, you need to create a superuser account.

### Step 1: Open Terminal in Backend Directory

```powershell
cd partsdb/backend
```

### Step 2: Activate Virtual Environment (if using one)

```powershell
# If you have a venv
.\.venv\Scripts\Activate.ps1

or

source .venv/Scripts/activate


# Or if using the venv folder
.\venv\Scripts\Activate.ps1
```

### Step 3: Create Superuser

```powershell
python partsdb\backend\manage.py createsuperuser
```

You will be prompted to enter:
- **Username**: Choose your admin username
- **Email address**: Your email (optional, can press Enter to skip)
- **Password**: Choose a strong password
- **Password (again)**: Confirm your password

Example:
```
Username: admin
Email address: admin@example.com
Password: ********
Password (again): ********
Superuser created successfully.
```

## Changing Admin Password

If you need to change an existing admin user's password:

### Method 1: Using Django Shell

```powershell
python manage.py shell
```

Then in the Python shell:
```python
from django.contrib.auth.models import User
user = User.objects.get(username='admin')
user.set_password('new_password_here')
user.save()
exit()
```

### Method 2: Using Change Password Command

```powershell
python manage.py changepassword admin
```

You'll be prompted to enter the new password twice.

## Accessing Django Admin

1. Start the Django server:
   ```powershell
   python manage.py runserver
   ```

2. Open your browser and go to:
   ```
   http://localhost:8000/admin/
   ```

3. Log in with your superuser credentials

## What You Can Do in Django Admin

- View and edit all components
- Manage inventory items
- View file attachments
- Manage user accounts
- View system logs
- Run database queries

## Security Best Practices

1. **Use Strong Passwords**: Minimum 12 characters with mix of uppercase, lowercase, numbers, and symbols
2. **Don't Share Credentials**: Each admin should have their own account
3. **Change Default Passwords**: Never use default passwords in production
4. **Regular Password Updates**: Change passwords periodically
5. **Enable HTTPS**: In production, always use HTTPS for admin access

## Creating Additional Admin Users

You can create multiple admin users:

```powershell
python manage.py createsuperuser
```

Or through the Django admin interface:
1. Log in to Django admin
2. Go to "Users"
3. Click "Add User"
4. After creating the user, edit them and check:
   - "Staff status" (allows admin access)
   - "Superuser status" (full permissions)

## Removing Admin Access

To revoke admin access from a user:

1. Log in to Django admin
2. Go to "Users"
3. Find the user
4. Uncheck "Staff status" and "Superuser status"
5. Save

## Forgot Password?

If you forgot your admin password and can't log in:

1. Use the shell method above to reset it
2. Or delete the user and create a new superuser:

```powershell
python manage.py shell
```

```python
from django.contrib.auth.models import User
User.objects.filter(username='admin').delete()
exit()
```

Then create a new superuser with `python manage.py createsuperuser`.

## Environment Variables

For production environments, you can set admin credentials via environment variables in your `.env` file or system:

```
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=your_secure_password
DJANGO_SUPERUSER_EMAIL=admin@example.com
```

Then create the superuser non-interactively:

```powershell
python manage.py createsuperuser --noinput
```
