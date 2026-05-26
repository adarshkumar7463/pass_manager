import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from apps.locations.models import Location, AdminLocation
from apps.passes.models import PassTemplate, Pass, PassVisit, PaymentRecord, LocationPassCounter

class Command(BaseCommand):
    help = 'Seeds the database with comprehensive demo data'

    def handle(self, *args, **options):
        self.stdout.write('Seeding data...')

        # 1. Create Superuser
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
            self.stdout.write(self.style.SUCCESS('Created superuser: admin / admin123'))

        # 2. Create Locations
        locations_data = [
            {'name': 'Golden Temple', 'slug': 'golden-temple', 'prefix': 'GT', 'price': 0, 'desc': 'Historical spiritual site.'},
            {'name': 'Museum of Art', 'slug': 'museum-art', 'prefix': 'MA', 'price': 500, 'desc': 'Exhibition of classical and modern art.'},
            {'name': 'Central Park Safari', 'slug': 'park-safari', 'prefix': 'CPS', 'price': 1200, 'desc': 'Wildlife safari experience.'},
            {'name': 'Sky High Observatory', 'slug': 'sky-high', 'prefix': 'SHO', 'price': 800, 'desc': 'City views from the 100th floor.'},
            {'name': 'Aqua World', 'slug': 'aqua-world', 'prefix': 'AW', 'price': 1000, 'desc': 'Largest underwater tunnel in the city.'},
            {'name': 'Ancient Ruins', 'slug': 'ancient-ruins', 'prefix': 'AR', 'price': 300, 'desc': 'Archaeological site with guided tours.'},
        ]

        locations = []
        for loc in locations_data:
            location, created = Location.objects.get_or_create(
                slug=loc['slug'],
                defaults={
                    'name': loc['name'],
                    'prefix': loc['prefix'],
                    'price': loc['price'],
                    'description': loc['desc'],
                    'address': f'123 {loc["name"]} St, Heritage Zone'
                }
            )
            locations.append(location)
            if created:
                LocationPassCounter.objects.get_or_create(location=location)
                self.stdout.write(f'Created location: {location.name}')

        # 3. Create Location Admins
        for i, loc in enumerate(locations):
            username = f'admin_{loc.prefix.lower()}'
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(username, f'{username}@example.com', 'pass123')
                AdminLocation.objects.create(user=user, location=loc, is_primary=True)
                self.stdout.write(f'Created location admin: {username} for {loc.name}')

        # 4. Create Pass Templates
        templates = []
        for loc in locations:
            # Standard Template
            template, _ = PassTemplate.objects.get_or_create(
                location=loc,
                name='Standard Pass',
                defaults={
                    'total_price': loc.price,
                    'internal_notes': f'Standard entry for {loc.name}',
                    'is_active': True
                }
            )
            templates.append(template)

            # Discounted Template (VIP/Student)
            if loc.price > 0:
                template_vip, _ = PassTemplate.objects.get_or_create(
                    location=loc,
                    name='VIP Pass',
                    defaults={
                        'total_price': loc.price * Decimal('1.5'),
                        'discount_percent': 0,
                        'internal_notes': 'Priority access and lounge usage.',
                        'is_active': True
                    }
                )
                templates.append(template_vip)

        # 5. Create some Passes
        names = ['Rajesh Kumar', 'Anita Singh', 'Vikram Mehra', 'Sonia Gandhi', 'Amit Shah', 'Priyanka Chopra']
        phones = ['9876543210', '9988776655', '9123456789', '8877665544', '7766554433', '6655443322']
        
        for i in range(15):
            template = random.choice(templates)
            counter, _ = LocationPassCounter.objects.get_or_create(location=template.location)
            unique_id = counter.next_id()
            
            p = Pass.objects.create(
                template=template,
                unique_id=unique_id,
                full_name=random.choice(names),
                phone=random.choice(phones),
                address='Sample Address, City, State',
                status=random.choice(['ACTIVE', 'ACTIVE', 'ACTIVE', 'EXPIRED']),
                created_at=timezone.now() - timezone.timedelta(days=random.randint(0, 30))
            )

            # Create payment record
            PaymentRecord.objects.create(
                pass_obj=p,
                amount_paid=template.total_price,
                payment_method=random.choice(['Cash', 'UPI', 'Card']),
                recorded_by=User.objects.first(),
                notes='Demo payment record'
            )

            # Create Visits
            # If it's a combo, we would have multiple visits. For now simple 1:1 or logic-based
            # The current model seems to imply 1 visit per pass usually, or multiple if template allows.
            # Let's create a visit for each location for this pass (simulating combo if prefix was COMBO, 
            # but let's just create one for the template's location)
            pv = PassVisit.objects.create(
                pass_obj=p,
                location=template.location,
                status='DONE' if p.status == 'EXPIRED' else random.choice(['PENDING', 'DONE']),
                visited_at=timezone.now() if p.status == 'EXPIRED' else None
            )
            
            if pv.status == 'DONE' and not pv.visited_at:
                pv.visited_at = timezone.now()
                pv.save()

        self.stdout.write(self.style.SUCCESS('Successfully seeded database with demo data'))
