import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create the initial superuser from temporary BOOTSTRAP_ADMIN_* environment variables.'

    def handle(self, *args, **options):
        username = os.environ.get('BOOTSTRAP_ADMIN_USERNAME', '').strip()
        password = os.environ.get('BOOTSTRAP_ADMIN_PASSWORD', '')

        # Makes it safe to leave this command in the start command after the
        # temporary variables have been removed from the hosting dashboard.
        if not username and not password:
            self.stdout.write('No bootstrap admin configured; skipping.')
            return
        if not username or not password:
            self.stderr.write('Set both BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD.')
            return

        user_model = get_user_model()
        user = user_model.objects.filter(username=username).first()
        reset_password = os.environ.get('BOOTSTRAP_ADMIN_RESET_PASSWORD', '').strip().lower() in {
            '1', 'true', 'yes', 'on'
        }
        if user:
            if reset_password:
                user.set_password(password)
                user.is_staff = True
                user.is_superuser = True
                user.save(update_fields=['password', 'is_staff', 'is_superuser'])
                self.stdout.write(self.style.SUCCESS(f'Password reset for superuser {username!r}.'))
                return
            self.stdout.write(f'Superuser {username!r} already exists; leaving it unchanged.')
            return

        email = os.environ.get('BOOTSTRAP_ADMIN_EMAIL', '').strip()
        user_model.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f'Superuser {username!r} created.'))
