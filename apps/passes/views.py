import json
import re
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from django.db import transaction
from .models import PassTemplate, Pass, LocationPassCounter, PaymentRecord, RateLimitLog


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def validate_phone(phone):
    cleaned = re.sub(r'[\s\-\(\)\+]', '', phone)
    return re.match(r'^\d{7,15}$', cleaned) is not None


# ─── PUBLIC: GENERATE PASS ────────────────────────────────────────────────────

def generate_pass_page(request, template_id):
    template = get_object_or_404(PassTemplate, id=template_id, is_active=True)

    if template.is_limit_reached:
        return render(request, 'passes/limit_reached.html', {'template': template})

    if request.method == 'POST':
        return handle_pass_submission(request, template)

    return render(request, 'passes/generate_pass.html', {'template': template})


@transaction.atomic
def handle_pass_submission(request, template):
    full_name = request.POST.get('full_name', '').strip()
    phone = request.POST.get('phone', '').strip()
    address = request.POST.get('address', '').strip()
    ip = get_client_ip(request)

    errors = []
    if not full_name or len(full_name) < 2:
        errors.append('Please enter your full name.')
    if not phone or not validate_phone(phone):
        errors.append('Please enter a valid phone number.')
    if not address or len(address) < 5:
        errors.append('Please enter your full address.')

    # Rate limiting
    from django.conf import settings as conf
    window_start = timezone.now() - timezone.timedelta(seconds=conf.RATE_LIMIT_WINDOW)
    recent_count = RateLimitLog.objects.filter(
        ip_address=ip, template=template, created_at__gte=window_start
    ).count()
    if recent_count >= conf.RATE_LIMIT_REQUESTS:
        errors.append('Too many requests. Please try again later.')

    if errors:
        return render(request, 'passes/generate_pass.html', {
            'template': template, 'errors': errors,
            'form_data': {'full_name': full_name, 'phone': phone, 'address': address}
        })

    # Generate unique ID
    counter, _ = LocationPassCounter.objects.get_or_create(location=template.location)
    unique_id = counter.next_id()

    # Create pass
    pass_obj = Pass.objects.create(
        template=template,
        unique_id=unique_id,
        full_name=full_name,
        phone=phone,
        address=address,
        status='ACTIVE',
        ip_address=ip,
    )

    # Always create visit records
    from apps.locations.models import Location
    from .models import PassVisit
    if template.location.prefix == 'COMBO':
        # Create visits for all 6 locations
        all_locs = Location.objects.filter(is_active=True).exclude(prefix='COMBO')
        for loc in all_locs:
            PassVisit.objects.create(pass_obj=pass_obj, location=loc)
    else:
        # Create visit for the single specific location
        PassVisit.objects.create(pass_obj=pass_obj, location=template.location)

    # Generate pass QR code
    try:
        pass_obj.generate_pass_qr(settings.SITE_URL)
    except Exception:
        pass  # QR generation is non-critical

    # Log rate limit
    RateLimitLog.objects.create(ip_address=ip, template=template)

    return redirect('passes:view_pass', unique_id=pass_obj.unique_id)


def view_pass(request, unique_id):
    pass_obj = get_object_or_404(Pass, unique_id=unique_id)
    visits = pass_obj.visits.all().select_related('location')
    return render(request, 'passes/view_pass.html', {
        'pass_obj': pass_obj,
        'visits': visits,
    })


def pass_pdf(request, unique_id):
    pass_obj = get_object_or_404(Pass, unique_id=unique_id)
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A6
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from io import BytesIO
        from django.core.files.storage import default_storage

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A6)
        w, h = A6

        # Background
        c.setFillColorRGB(0.1, 0.1, 0.18)
        c.rect(0, 0, w, h, fill=1, stroke=0)

        # Header band
        c.setFillColorRGB(0.4, 0.2, 0.8)
        c.rect(0, h - 30*mm, w, 30*mm, fill=1, stroke=0)

        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(w/2, h - 18*mm, pass_obj.location.name)
        c.setFont("Helvetica", 9)
        c.drawCentredString(w/2, h - 25*mm, "ENTRY PASS")

        # Unique ID
        c.setFillColorRGB(0.4, 0.8, 1)
        c.setFont("Helvetica-Bold", 28)
        c.drawCentredString(w/2, h - 48*mm, pass_obj.unique_id)

        # Details
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(10*mm, h - 62*mm, f"Name: {pass_obj.full_name}")
        c.setFont("Helvetica", 9)
        c.drawString(10*mm, h - 70*mm, f"Phone: {pass_obj.phone}")

        c.setFont("Helvetica-Bold", 11)
        c.setFillColorRGB(0.4, 0.8, 1)
        c.drawString(10*mm, h - 82*mm, f"Discount: {pass_obj.template.discount_percent}%")
        c.drawString(10*mm, h - 90*mm, f"Price: {pass_obj.template.total_price}")

        # Status badge
        if pass_obj.status == 'ACTIVE':
            c.setFillColorRGB(0.2, 0.8, 0.4)
        else:
            c.setFillColorRGB(0.9, 0.2, 0.2)
        c.roundRect(w/2 - 20*mm, h - 96*mm, 40*mm, 10*mm, 2*mm, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(w/2, h - 90*mm, pass_obj.status)

        # Payment note
        c.setFillColorRGB(0.8, 0.8, 0.8)
        c.setFont("Helvetica", 8)
        c.drawCentredString(w/2, 8*mm, pass_obj.template.payment_note)

        c.showPage()
        c.save()
        buf.seek(0)

        response = HttpResponse(buf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="pass_{pass_obj.unique_id}.pdf"'
        return response
    except ImportError:
        messages.error(request, 'PDF generation requires reportlab. Please install it.')
        return redirect('passes:view_pass', unique_id=unique_id)


# ─── ADMIN: VALIDATE PASS ──────────────────────────────────────────────────────

@login_required
def validate_pass_page(request):
    location = get_active_admin_location(request)
    return render(request, 'admin_panel/validate.html', {'location': location})


@login_required
def validate_pass_lookup(request):
    unique_id = request.GET.get('id', '').strip().upper()
    if not unique_id:
        return JsonResponse({'error': 'No ID provided'}, status=400)

    try:
        pass_obj = Pass.objects.select_related('template__location').get(unique_id=unique_id)
    except Pass.DoesNotExist:
        return JsonResponse({'error': 'Pass not found', 'unique_id': unique_id}, status=404)

    # Check if admin has access to this pass's location or if it's an All-Locations Combo pass
    if not request.user.is_superuser:
        is_combo = (pass_obj.location.prefix == 'COMBO')
        allowed = request.user.admin_locations.filter(location=pass_obj.location).exists()
        if not allowed and not is_combo:
            return JsonResponse({'error': 'Access denied for this location'}, status=403)

    has_payment = hasattr(pass_obj, 'payment')
    
    # Get visit stats for the JSON response
    visits_data = []
    from apps.locations.models import AdminLocation
    user_locations = AdminLocation.objects.filter(user=request.user).values_list('location_id', flat=True)
    
    for v in pass_obj.visits.all().select_related('location'):
        visits_data.append({
            'prefix': v.location.prefix,
            'location': v.location.name,
            'status': v.status,
            'visited_at': v.visited_at.strftime('%d %b, %I:%M %p') if v.visited_at else None,
            'scannable_by_me': request.user.is_superuser or v.location_id in user_locations,
        })

    return JsonResponse({
        'unique_id': pass_obj.unique_id,
        'full_name': pass_obj.full_name,
        'phone': pass_obj.phone,
        'status': pass_obj.status,
        'location': pass_obj.location.name,
        'discount': str(pass_obj.template.discount_percent),
        'price': str(pass_obj.template.total_price),
        'created_at': pass_obj.created_at.strftime('%d %b %Y, %I:%M %p'),
        'has_payment': has_payment,
        'payment_method': pass_obj.payment.payment_method if has_payment else None,
        'visits': visits_data,
        'total_locations': pass_obj.total_locations,
        'visits_done': pass_obj.visits_done,
        'progress': pass_obj.progress_percent,
    })


@login_required
@require_http_methods(['POST'])
def expire_pass(request, unique_id):
    pass_obj = get_object_or_404(Pass, unique_id=unique_id)
    if not request.user.is_superuser:
        is_combo = (pass_obj.location.prefix == 'COMBO')
        allowed = request.user.admin_locations.filter(location=pass_obj.location).exists()
        if not allowed and not is_combo:
            return JsonResponse({'error': 'Access denied'}, status=403)

    pass_obj.expire()
    return JsonResponse({'success': True, 'status': 'EXPIRED'})


@login_required
@require_http_methods(['POST'])
def mark_payment(request, unique_id):
    pass_obj = get_object_or_404(Pass, unique_id=unique_id)
    if not request.user.is_superuser:
        is_combo = (pass_obj.location.prefix == 'COMBO')
        allowed = request.user.admin_locations.filter(location=pass_obj.location).exists()
        if not allowed and not is_combo:
            return JsonResponse({'error': 'Access denied'}, status=403)

    try:
        data = json.loads(request.body)
    except Exception:
        data = {}

    amount = data.get('amount', str(pass_obj.template.total_price))
    method = data.get('method', 'Cash')

    if not hasattr(pass_obj, 'payment'):
        PaymentRecord.objects.create(
            pass_obj=pass_obj,
            amount_paid=amount,
            payment_method=method,
            recorded_by=request.user,
        )
    pass_obj.mark_used()
    return JsonResponse({'success': True, 'status': 'USED'})


# ─── ADMIN: DASHBOARD & TEMPLATES ─────────────────────────────────────────────

@login_required
def admin_dashboard(request):
    from apps.locations.models import Location, AdminLocation
    
    is_location_admin = not request.user.is_superuser
    
    if request.user.is_superuser:
        locations = Location.objects.all()
        templates = PassTemplate.objects.select_related('location').all()[:10]
        total_passes = Pass.objects.count()
        active_passes = Pass.objects.filter(status='ACTIVE').count()
        expired_passes = Pass.objects.filter(status='EXPIRED').count()
        used_passes = Pass.objects.filter(status='USED').count()
        
        loc_stats = []
        for loc in locations:
            loc_stats.append({
                'location': loc,
                'total': Pass.objects.filter(template__location=loc).count(),
                'done': Pass.objects.filter(template__location=loc, status='USED').count(),
            })
            
        return render(request, 'admin_panel/dashboard.html', {
            'is_location_admin': False,
            'locations': locations,
            'loc_stats': loc_stats,
            'templates': templates,
            'total_passes': total_passes,
            'active_passes': active_passes,
            'expired_passes': expired_passes,
            'used_passes': used_passes,
            'total_visits': total_passes * 6, # approximate
            'done_visits': used_passes,
        })
    else:
        location = request.user.admin_locations.first().location if request.user.admin_locations.exists() else None
        location_ids = request.user.admin_locations.values_list('location_id', flat=True)
        locations = Location.objects.filter(id__in=location_ids)
        templates = PassTemplate.objects.filter(location__in=locations).select_related('location')[:10]
        
        total_passes = Pass.objects.filter(template__location__in=locations).count()
        active_passes = Pass.objects.filter(template__location__in=locations, status='ACTIVE').count()
        expired_passes = Pass.objects.filter(template__location__in=locations, status='EXPIRED').count()
        used_passes = Pass.objects.filter(template__location__in=locations, status='USED').count()

        recent_visits = PaymentRecord.objects.filter(pass_obj__template__location=location).order_by('-created_at')[:10] if location else []
        
        return render(request, 'admin_panel/dashboard.html', {
            'is_location_admin': True,
            'location': location,
            'locations': locations,
            'templates': templates,
            'stats': {
                'total': total_passes,
                'done': used_passes,
                'pending': active_passes,
                'today': Pass.objects.filter(template__location=location, created_at__date=timezone.now().date()).count() if location else 0
            },
            'recent_visits': recent_visits,
        })


@login_required
def template_create(request):
    from apps.locations.models import Location
    if request.user.is_superuser:
        locations = Location.objects.filter(is_active=True)
    else:
        location_ids = request.user.admin_locations.values_list('location_id', flat=True)
        locations = Location.objects.filter(id__in=location_ids, is_active=True)

    if request.method == 'POST':
        loc_id = request.POST.get('location')
        name = request.POST.get('name', '').strip()
        discount = request.POST.get('discount_percent', '0')
        price = request.POST.get('total_price', '0')
        access_limit = request.POST.get('access_limit', '').strip()
        internal_notes = request.POST.get('internal_notes', '').strip()

        try:
            location = locations.get(id=loc_id)
        except Exception:
            messages.error(request, 'Invalid location selected.')
            return render(request, 'admin_panel/template_form.html', {'locations': locations})

        template = PassTemplate.objects.create(
            location=location,
            name=name,
            discount_percent=float(discount),
            total_price=float(price),
            access_limit=int(access_limit) if access_limit else None,
            internal_notes=internal_notes,
        )

        try:
            template.generate_qr(settings.SITE_URL)
        except Exception as e:
            messages.warning(request, f'Template created but QR generation failed: {e}')

        messages.success(request, f'Pass template "{template.name}" created with QR code.')
        return redirect('passes:template_detail', pk=template.id)

    return render(request, 'admin_panel/template_form.html', {'locations': locations})


@login_required
def template_list(request):
    from apps.locations.models import Location
    if request.user.is_superuser:
        templates = PassTemplate.objects.select_related('location').all()
    else:
        location_ids = request.user.admin_locations.values_list('location_id', flat=True)
        templates = PassTemplate.objects.filter(location__id__in=location_ids).select_related('location')

    return render(request, 'admin_panel/template_list.html', {'templates': templates})


@login_required
def template_detail(request, pk):
    template = get_object_or_404(PassTemplate, pk=pk)
    if not request.user.is_superuser:
        allowed = request.user.admin_locations.filter(location=template.location).exists()
        if not allowed:
            messages.error(request, 'Access denied.')
            return redirect('passes:template_list')

    passes = template.passes.all()[:50]
    qr_url = f"{settings.SITE_URL}/generate-pass/{template.id}/"
    return render(request, 'admin_panel/template_detail.html', {
        'template': template, 'passes': passes, 'qr_url': qr_url
    })


@login_required
def toggle_template(request, pk):
    template = get_object_or_404(PassTemplate, pk=pk)
    template.is_active = not template.is_active
    template.save()
    return JsonResponse({'is_active': template.is_active})


@login_required
def passes_list(request):
    from apps.locations.models import Location
    if request.user.is_superuser:
        passes = Pass.objects.select_related('template__location').all()
    else:
        from django.db.models import Q
        location_ids = request.user.admin_locations.values_list('location_id', flat=True)
        # Show my location passes OR all COMBO passes
        passes = Pass.objects.filter(
            Q(template__location__id__in=location_ids) | 
            Q(template__location__prefix='COMBO')
        ).select_related('template__location')

    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')
    if status_filter:
        passes = passes.filter(status=status_filter)
    if search:
        passes = passes.filter(unique_id__icontains=search) | passes.filter(full_name__icontains=search)

    return render(request, 'admin_panel/passes_list.html', {'passes': passes, 'status_filter': status_filter, 'search': search})


@login_required
def analytics(request):
    from apps.locations.models import Location
    from django.db.models import Count
    from django.db.models.functions import TruncDate

    if request.user.is_superuser:
        locations = Location.objects.all()
        all_passes = Pass.objects.all()
    else:
        location_ids = request.user.admin_locations.values_list('location_id', flat=True)
        locations = Location.objects.filter(id__in=location_ids)
        all_passes = Pass.objects.filter(template__location__in=locations)

    # Daily stats (last 14 days)
    from datetime import datetime, timedelta
    two_weeks_ago = timezone.now() - timedelta(days=14)
    daily_stats = all_passes.filter(created_at__gte=two_weeks_ago).annotate(
        date=TruncDate('created_at')
    ).values('date').annotate(count=Count('id')).order_by('date')

    # Per location stats
    location_stats = []
    for loc in locations:
        loc_passes = all_passes.filter(template__location=loc)
        location_stats.append({
            'name': loc.name,
            'total': loc_passes.count(),
            'active': loc_passes.filter(status='ACTIVE').count(),
            'used': loc_passes.filter(status='USED').count(),
            'expired': loc_passes.filter(status='EXPIRED').count(),
        })

    return render(request, 'admin_panel/analytics.html', {
        'location_stats': location_stats,
        'daily_stats': list(daily_stats),
        'total': all_passes.count(),
    })


def get_active_admin_location(request):
    """Helper to get admin's primary location"""
    if request.user.is_superuser:
        from apps.locations.models import Location
        return Location.objects.first()
    al = request.user.admin_locations.filter(is_primary=True).first()
    if not al:
        al = request.user.admin_locations.first()
    return al.location if al else None


# ─── PUBLIC: SCAN / LOCATION VISIT ────────────────────────────────────────────

@login_required
def scan_visit_page(request, unique_id, prefix):
    """Show the scan landing page for a location visit QR code."""
    pass_obj = get_object_or_404(Pass, unique_id=unique_id)
    from apps.locations.models import Location
    location = get_object_or_404(Location, prefix=prefix)
    
    from .models import PassVisit
    visit = PassVisit.objects.filter(pass_obj=pass_obj, location=location).first()
    already_done = visit.status == 'DONE' if visit else False
    
    return render(request, 'passes/scan_visit.html', {
        'pass_obj': pass_obj,
        'location': location,
        'prefix': prefix,
        'already_done': already_done,
        'visit': visit,
    })


@login_required
@require_http_methods(['POST'])
def mark_visit_done(request, unique_id, prefix):
    """Mark a location visit as done (called from scan landing page)."""
    pass_obj = get_object_or_404(Pass, unique_id=unique_id)
    from apps.locations.models import Location
    location = get_object_or_404(Location, prefix=prefix)

    # Permission check: Admin must be assigned to THIS location to mark it done
    if not request.user.is_superuser:
        allowed = request.user.admin_locations.filter(location=location).exists()
        if not allowed:
            return JsonResponse({'error': 'Access denied for this location'}, status=403)

    from .models import PassVisit
    visit = get_object_or_404(PassVisit, pass_obj=pass_obj, location=location)
    
    if visit.status == 'PENDING':
        visit.mark_done()

    return JsonResponse({
        'success': True,
        'status': visit.status,
        'unique_id': pass_obj.unique_id,
        'location': location.name,
    })
