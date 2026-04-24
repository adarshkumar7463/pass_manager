"""python manage.py setup_demo"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Set up PassManager with locations, combo template, and admin users'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='admin')
        parser.add_argument('--password', default='admin123')

    def handle(self, *args, **options):
        from apps.locations.models import Location, AdminLocation
        from apps.passes.models import PassTemplate, GlobalPassCounter
        from django.conf import settings
        from django.utils.text import slugify

        # 1. Superuser
        if not User.objects.filter(username=options['username']).exists():
            User.objects.create_superuser(options['username'], 'admin@example.com', options['password'])
            self.stdout.write(self.style.SUCCESS(f"✅ Superuser: {options['username']} / {options['password']}"))
        else:
            self.stdout.write(f"ℹ️  Superuser '{options['username']}' exists.")

        # 2. Locations
        LOCATIONS = [
            ('Tip N Top Viewpoint',        'TT', 'The highest point providing breathtaking sunrise/sunset views and a popular, peaceful vantage point.'),
            ('Bhulla Tal Lake',             'BT', 'A tranquil, army-maintained man-made lake perfect for picnics, boating, and families.'),
            ('Darwan Singh Museum',         'DS', 'A well-maintained, two-story museum showcasing the history and artifacts of the Garhwal Rifles.'),
            ("St. Mary's Church",           'SM', "Historic British-era church offering beautiful architecture and a peaceful ambiance."),
            ('Garhwal Rifles War Memorial', 'GR', 'A significant, highly-visited site dedicated to the Indian Army.'),
            ('Tarkeshwar Mahadev Temple',   'TM', 'A serene, ancient temple surrounded by thick deodar forests, located about 35 km from the main town.'),
        ]
        for i, (name, prefix, desc) in enumerate(LOCATIONS):
            loc, created = Location.objects.get_or_create(
                prefix=prefix,
                defaults={'name': name, 'slug': slugify(name), 'description': desc, 'order': i, 'is_active': True}
            )
            self.stdout.write(f"{'✅ Created' if created else 'ℹ️  Exists'}: {loc.name} ({loc.prefix})")

        # 3. Combo template
        template = PassTemplate.objects.first()
        if not template:
            template = PassTemplate.objects.create(
                name='All-Locations Combo Pass',
                discount_percent=10,
                total_price=600,
                internal_notes='Master combo template — covers all 6 Lansdowne locations',
            )
            try:
                template.generate_qr(settings.SITE_URL)
                self.stdout.write(self.style.SUCCESS(f"✅ Combo template created with QR"))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️  Template created, QR failed: {e}"))
        else:
            self.stdout.write(f"ℹ️  Template exists: {template.name}")

        # 4. Initialize counter
        GlobalPassCounter.objects.get_or_create(pk=1)

        # 5. Create one location admin per location
        for name, prefix, desc in LOCATIONS:
            loc = Location.objects.get(prefix=prefix)
            username = f"admin_{prefix.lower()}"
            if not User.objects.filter(username=username).exists():
                u = User.objects.create_user(username=username, password=options['password'], email=f"{username}@example.com")
                AdminLocation.objects.create(user=u, location=loc)
                self.stdout.write(self.style.SUCCESS(f"✅ Location admin: {username} / {options['password']} → {loc.name}"))
            else:
                self.stdout.write(f"ℹ️  Admin {username} exists")

        self.stdout.write(self.style.SUCCESS(
            f"\n🚀 Setup complete!\n"
            f"   Superadmin:     {options['username']} / {options['password']}\n"
            f"   Location admins: admin_tt, admin_bt, admin_ds, admin_sm, admin_gr, admin_tm (same password)\n"
            f"   Admin URL:      http://localhost:8000/admin-panel/login/\n"
            f"   Pass URL:       http://localhost:8000/generate-pass/{template.id}/\n"
        ))