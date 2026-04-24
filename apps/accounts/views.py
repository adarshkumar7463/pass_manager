from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from apps.locations.models import Location, AdminLocation


def login_view(request):
    if request.user.is_authenticated:
        return redirect('passes:dashboard')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            # Show which location they're logged in as
            al = user.admin_locations.first()
            if al:
                messages.success(request, f'Welcome! Logged in as admin of {al.location.name}')
            elif user.is_superuser:
                messages.success(request, 'Welcome, Superadmin.')
            return redirect(request.GET.get('next', 'passes:dashboard'))
        messages.error(request, 'Invalid username or password.')
    return render(request, 'admin_panel/login.html')


def logout_view(request):
    logout(request)
    return redirect('accounts:login')


@login_required
def profile_view(request):
    user = request.user
    admin_locations = user.admin_locations.select_related('location').all()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'change_password':
            old_pw = request.POST.get('old_password', '')
            new_pw = request.POST.get('new_password', '')
            confirm_pw = request.POST.get('confirm_password', '')
            if not user.check_password(old_pw):
                messages.error(request, 'Current password is incorrect.')
            elif len(new_pw) < 6:
                messages.error(request, 'New password must be at least 6 characters.')
            elif new_pw != confirm_pw:
                messages.error(request, 'Passwords do not match.')
            else:
                user.set_password(new_pw)
                user.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, user)
                messages.success(request, 'Password changed successfully.')
        return redirect('accounts:profile')

    return render(request, 'admin_panel/profile.html', {
        'user': user,
        'admin_locations': admin_locations,
    })


@login_required
def admin_users(request):
    if not request.user.is_superuser:
        messages.error(request, 'Superadmin access required.')
        return redirect('passes:dashboard')
    users = User.objects.prefetch_related('admin_locations__location').all()
    locations = Location.objects.all()
    return render(request, 'admin_panel/users.html', {'users': users, 'locations': locations})


@login_required
def create_admin_user(request):
    if not request.user.is_superuser:
        messages.error(request, 'Superadmin access required.')
        return redirect('passes:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        email = request.POST.get('email', '').strip()
        location_id = request.POST.get('location')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
        elif not password or len(password) < 6:
            messages.error(request, 'Password must be at least 6 characters.')
        elif not location_id:
            messages.error(request, 'Please assign a location.')
        else:
            try:
                loc = Location.objects.get(id=location_id)
                user = User.objects.create_user(username=username, password=password, email=email)
                AdminLocation.objects.create(user=user, location=loc)
                messages.success(request, f'Admin "{username}" created for {loc.name}.')
                return redirect('accounts:admin_users')
            except Location.DoesNotExist:
                messages.error(request, 'Invalid location.')

    locations = Location.objects.filter(is_active=True)
    return render(request, 'admin_panel/create_user.html', {'locations': locations})