from django.db import models
from django.contrib.auth.models import User


class Location(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    image = models.ImageField(upload_to='locations/', blank=True, null=True)
    description = models.TextField(blank=True)
    address = models.TextField(blank=True)
    prefix = models.CharField(max_length=5, unique=True, help_text='Used for pass IDs e.g. A, B, LOC1')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_pass_count(self):
        return self.passtemplates.aggregate(
            total=models.Sum('passes__id')
        )['total'] or 0


class AdminLocation(models.Model):
    """Links admin users to locations they can manage"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_locations')
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='admins')
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'location')

    def __str__(self):
        return f"{self.user.username} → {self.location.name}"
