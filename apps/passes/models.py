from django.db import models
from django.utils import timezone
from apps.locations.models import Location


class PassTemplate(models.Model):
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='passtemplates')
    name = models.CharField(max_length=200, help_text='Internal template name')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    access_limit = models.PositiveIntegerField(null=True, blank=True, help_text='Leave blank for unlimited')
    internal_notes = models.TextField(blank=True)
    payment_note = models.CharField(
        max_length=300,
        default='💳 Payment will be done at counter'
    )
    is_active = models.BooleanField(default=True)
    qr_code = models.ImageField(upload_to='qrcodes/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.location.name} — {self.name}"

    @property
    def passes_count(self):
        return self.passes.count()

    @property
    def active_passes_count(self):
        return self.passes.filter(status='ACTIVE').count()

    @property
    def is_limit_reached(self):
        if self.access_limit is None:
            return False
        return self.passes_count >= self.access_limit

    def generate_qr(self, base_url):
        import qrcode
        import io
        from django.core.files.base import ContentFile

        url = f"{base_url}/generate-pass/{self.id}/"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1a1a2e", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        filename = f"qr_template_{self.id}.png"
        self.qr_code.save(filename, ContentFile(buf.read()), save=True)


class Pass(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('USED', 'Used'),
    ]

    template = models.ForeignKey(PassTemplate, on_delete=models.CASCADE, related_name='passes')
    unique_id = models.CharField(max_length=20, unique=True, db_index=True)
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    address = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    expired_at = models.DateTimeField(null=True, blank=True)
    pass_qr = models.ImageField(upload_to='pass_qr/', blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.unique_id} — {self.full_name}"

    @property
    def location(self):
        return self.template.location

    @property
    def total_locations(self):
        if self.template.location.prefix == 'COMBO':
            return 6
        return 1

    @property
    def visits_done(self):
        return self.visits.filter(status='DONE').count()

    @property
    def progress_percent(self):
        total = self.total_locations
        if total == 0:
            return 0
        return int((self.visits_done / total) * 100)

    def expire(self):
        self.status = 'EXPIRED'
        self.expired_at = timezone.now()
        self.save()

    def mark_used(self):
        self.status = 'USED'
        self.validated_at = timezone.now()
        self.save()

    def generate_pass_qr(self, base_url):
        import qrcode
        import io
        from django.core.files.base import ContentFile

        url = f"{base_url}/pass/{self.unique_id}/"
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=8, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1a1a2e", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        self.pass_qr.save(f"pass_{self.unique_id}.png", ContentFile(buf.read()), save=True)

        # Also generate QR codes for each visit
        for visit in self.visits.all():
            visit.generate_qr(base_url)


class PassVisit(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('DONE', 'Done'),
    ]
    pass_obj = models.ForeignKey(Pass, on_delete=models.CASCADE, related_name='visits')
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    visited_at = models.DateTimeField(null=True, blank=True)
    qr_code = models.ImageField(upload_to='visit_qrcodes/', blank=True, null=True)

    def __str__(self):
        return f"{self.pass_obj.unique_id} @ {self.location.name} — {self.status}"

    def mark_done(self):
        self.status = 'DONE'
        self.visited_at = timezone.now()
        self.save()
        
        # If all visits are done, mark the main pass as EXPIRED (Completed)
        if self.pass_obj.visits_done == self.pass_obj.total_locations:
            self.pass_obj.expire()

    def generate_qr(self, base_url):
        import qrcode
        import io
        from django.core.files.base import ContentFile

        # This URL is scanned by the location admin to mark this specific visit as done
        url = f"{base_url}/scan/{self.pass_obj.unique_id}/{self.location.prefix}/"
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=5, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1a1a2e", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        self.qr_code.save(f"visit_{self.pass_obj.unique_id}_{self.location.prefix}.png", ContentFile(buf.read()), save=True)


class LocationPassCounter(models.Model):
    """Tracks auto-increment counters per location for unique IDs"""
    location = models.OneToOneField(Location, on_delete=models.CASCADE, related_name='pass_counter')
    current_count = models.PositiveIntegerField(default=0)

    def next_id(self):
        self.current_count += 1
        self.save()
        return f"{self.location.prefix}-{str(self.current_count).zfill(3)}"

    def __str__(self):
        return f"{self.location.name}: {self.current_count}"


class PaymentRecord(models.Model):
    pass_obj = models.OneToOneField(Pass, on_delete=models.CASCADE, related_name='payment')
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, default='Cash')
    recorded_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment for {self.pass_obj.unique_id} — ₹{self.amount_paid}"


class RateLimitLog(models.Model):
    ip_address = models.GenericIPAddressField()
    template = models.ForeignKey(PassTemplate, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['ip_address', 'template', 'created_at'])]
