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
        'is_print': False,
    })


def print_pass(request, unique_id):
    pass_obj = get_object_or_404(Pass, unique_id=unique_id)
    visits = pass_obj.visits.all().select_related('location')
    return render(request, 'passes/view_pass.html', {
        'pass_obj': pass_obj,
        'visits': visits,
        'is_print': True,
    })


def pass_pdf(request, unique_id):
    pass_obj = get_object_or_404(Pass, unique_id=unique_id)
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A6
        from reportlab.lib.units import mm
        from io import BytesIO

        buf = BytesIO()
        from reportlab.lib.pagesizes import landscape
        c = canvas.Canvas(buf, pagesize=landscape(A6))
        _draw_pass_page(c, pass_obj, request)
        c.save()
        buf.seek(0)

        response = HttpResponse(buf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="pass_{pass_obj.unique_id}.pdf"'
        return response
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        messages.error(request, f'PDF generation failed: {e}')
        return redirect('passes:view_pass', unique_id=unique_id)


@login_required
def bulk_print_view(request, template_id):
    template = get_object_or_404(PassTemplate, id=template_id)
    passes = template.passes.all().prefetch_related('visits__location')
    return render(request, 'admin_panel/bulk_print.html', {
        'template': template,
        'passes': passes,
    })


@login_required
def bulk_pass_pdf(request, template_id):
    template = get_object_or_404(PassTemplate, id=template_id)
    passes = template.passes.all().prefetch_related('visits__location')
    
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.units import mm
        from io import BytesIO

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=landscape(A4))
        w, h = landscape(A4)
        
        # Grid settings for 2 columns, 2 rows (4 per page)
        cols = 2
        rows = 2
        margin_x = 0.5*mm # Minimal margin for 296/297 fit
        margin_y = 0*mm 
        cell_w = 148.5*mm
        cell_h = 105*mm
        
        # Scale factor: 1.0 because A6 (148x105) * 2 matches A4 (297x210)
        scale = 1.0
        
        for i, pass_obj in enumerate(passes):
            if i > 0 and i % 4 == 0:
                c.showPage()
            
            idx = i % 4
            col = idx % cols
            row = idx // cols # 0 or 1
            
            # Position (Reportlab (0,0) is bottom left)
            px = margin_x + col * cell_w
            py = h - margin_y - (row + 1) * cell_h
            
            c.saveState()
            c.translate(px, py)
            c.scale(scale, scale)
            _draw_pass_content(c, pass_obj, request)
            c.restoreState()
            
        c.save()
        buf.seek(0)

        response = HttpResponse(buf, content_type='application/pdf')
        filename = f"batch_{template_id}_passes.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        messages.error(request, f'Bulk PDF generation failed: {e}')
        return redirect('passes:template_detail', pk=template_id)


def _draw_pass_page(c, pass_obj, request):
    # Single pass view still uses A6 Landscape
    from reportlab.lib.pagesizes import A6, landscape
    _draw_pass_content(c, pass_obj, request)


def _draw_pass_content(c, pass_obj, request):
    from reportlab.lib.pagesizes import A6, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    import qrcode
    from io import BytesIO
    from reportlab.lib.utils import ImageReader

    # Base dimensions: 148mm wide, 105mm high
    w, h = landscape(A6)
    
    # 1. Sidebar (Dark)
    sidebar_w = 40*mm
    c.setFillColorRGB(0.12, 0.12, 0.18) 
    c.rect(0, 0, sidebar_w, h, fill=1, stroke=0)
    
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(sidebar_w/2, h - 10*mm, "COMBO PASS")
    
    c.saveState()
    c.translate(sidebar_w/2, h/2)
    c.rotate(90)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(0, -5*mm, pass_obj.template.name.upper())
    c.restoreState()
    
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(sidebar_w/2, 10*mm, "ALL LOCATIONS")

    # 2. Main Area
    main_x = sidebar_w
    main_w = w - sidebar_w
    c.setFillColorRGB(0.98, 0.98, 1.0) 
    c.rect(main_x, 0, main_w, h, fill=1, stroke=0)
    
    c.setFillColorRGB(0.4, 0.3, 0.8) 
    c.setFont("Helvetica-Bold", 14)
    c.drawString(main_x + 10*mm, h - 15*mm, pass_obj.unique_id)
    
    c.saveState()
    status_text = f"{pass_obj.visits_done}/{pass_obj.total_locations} VISITED"
    c.setFillColorRGB(0.9, 1.0, 0.9)
    c.roundRect(w - 35*mm, h - 17*mm, 25*mm, 6*mm, 2*mm, fill=1, stroke=0)
    c.setFillColorRGB(0.1, 0.4, 0.2)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(w - 22.5*mm, h - 13*mm, status_text)
    c.restoreState()

    c.setStrokeColorRGB(0.9, 0.9, 0.9)
    c.line(main_x + 10*mm, h - 22*mm, w - 10*mm, h - 22*mm)

    info_w = 45*mm
    qr_grid_x = main_x + info_w + 5*mm
    
    c.setFillColorRGB(0.5, 0.5, 0.6)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(main_x + 10*mm, h - 30*mm, "HOLDER")
    c.setFillColorRGB(0.3, 0.2, 0.7)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(main_x + 10*mm, h - 35*mm, pass_obj.full_name)
    
    c.setFillColorRGB(0.5, 0.5, 0.6)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(main_x + 10*mm, h - 45*mm, "PHONE")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawString(main_x + 10*mm, h - 50*mm, pass_obj.phone)

    c.setFillColorRGB(0.5, 0.5, 0.6)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(main_x + 10*mm, h - 60*mm, "ISSUED")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawString(main_x + 10*mm, h - 65*mm, pass_obj.created_at.strftime("%d %b %Y"))

    c.setFillColorRGB(0.95, 1.0, 0.95)
    c.roundRect(main_x + 8*mm, 5*mm, info_w, 15*mm, 2*mm, fill=1, stroke=0)
    c.setFillColorRGB(0.1, 0.4, 0.2)
    c.setFont("Helvetica-Bold", 6)
    c.drawString(main_x + 10*mm, 16*mm, f"PRICE: ₹{pass_obj.template.total_price}")
    c.setFont("Helvetica-Bold", 5)
    c.drawString(main_x + 10*mm, 12*mm, "PAYMENT NOTE")
    c.setFont("Helvetica", 5)
    c.drawString(main_x + 10*mm, 9*mm, "Payment will be done at counter")

    # 4. QR Grid
    visits = list(pass_obj.visits.all().select_related('location'))
    qr_size = 18*mm
    gap = 2*mm
    
    c.setFillColorRGB(0.4, 0.3, 0.8)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(qr_grid_x, h - 30*mm, "SHOW QR AT COUNTER")
    
    for i, visit in enumerate(visits):
        row = i // 3
        col = i % 3
        qx = qr_grid_x + col * (qr_size + gap)
        qy = h - 40*mm - row * (qr_size + 10*mm)
        
        c.setStrokeColorRGB(0.9, 0.9, 0.9)
        c.roundRect(qx, qy, qr_size, qr_size + 5*mm, 1*mm, stroke=1, fill=0)
        
        c.setFillColorRGB(0.4, 0.3, 0.8)
        c.setFont("Helvetica-Bold", 5)
        c.drawCentredString(qx + qr_size/2, qy + qr_size + 2*mm, visit.location.prefix)
        
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 4)
        c.drawCentredString(qx + qr_size/2, qy + qr_size - 1*mm, visit.location.name[:15])

        base_url = f"{request.scheme}://{request.get_host()}"
        scan_url = f"{base_url}/scan/{pass_obj.unique_id}/{visit.location.prefix}/"
        
        qr = qrcode.QRCode(version=1, box_size=5, border=1)
        qr.add_data(scan_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        qr_buf = BytesIO()
        img.save(qr_buf, format='PNG')
        qr_buf.seek(0)
        c.drawImage(ImageReader(qr_buf), qx + 1*mm, qy + 1*mm, width=qr_size - 2*mm, height=qr_size - 2*mm)

        
        if visit.status == 'DONE':
            c.setStrokeColor(colors.green)
            c.setLineWidth(1)
            c.line(qx, qy, qx + qr_size, qy + qr_size + 5*mm)
            c.line(qx, qy + qr_size + 5*mm, qx + qr_size, qy)




# ─── ADMIN: VALIDATE PASS ──────────────────────────────────────────────────────

@login_required
def validate_pass_page(request):
    location = get_active_admin_location(request)
    user_prefixes = list(request.user.admin_locations.values_list('location__prefix', flat=True))
    return render(request, 'admin_panel/validate.html', {
        'location': location,
        'user_prefixes': json.dumps(user_prefixes)
    })


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
            
        from .models import PassVisit
        total_visits = PassVisit.objects.count()
        done_visits = PassVisit.objects.filter(status='DONE').count()
            
        return render(request, 'admin_panel/dashboard.html', {
            'is_location_admin': False,
            'locations': locations,
            'loc_stats': loc_stats,
            'templates': templates,
            'total_passes': total_passes,
            'active_passes': active_passes,
            'expired_passes': expired_passes,
            'used_passes': used_passes,
            'total_visits': total_visits,
            'done_visits': done_visits,
        })
    else:
        location = request.user.admin_locations.first().location if request.user.admin_locations.exists() else None
        location_ids = request.user.admin_locations.values_list('location_id', flat=True)
        locations = Location.objects.filter(id__in=location_ids)
        
        from .models import PassVisit
        # Total passes = passes for this location + all COMBO passes
        from django.db.models import Q
        all_passes = Pass.objects.filter(
            Q(template__location__in=locations) | 
            Q(template__location__prefix='COMBO')
        )
        
        total_passes_count = all_passes.count()
        
        # Visits stats for THIS specific location
        if location:
            done_count = PassVisit.objects.filter(location=location, status='DONE').count()
            pending_count = PassVisit.objects.filter(location=location, status='PENDING').count()
            today_count = PassVisit.objects.filter(
                location=location, 
                status='DONE', 
                visited_at__date=timezone.now().date()
            ).count()
            recent_visits = PassVisit.objects.filter(
                location=location, 
                status='DONE'
            ).select_related('pass_obj', 'pass_obj__payment').order_by('-visited_at')[:10]
        else:
            done_count = pending_count = today_count = 0
            recent_visits = []
            
        templates = PassTemplate.objects.filter(location__in=locations).select_related('location')[:10]
        
        return render(request, 'admin_panel/dashboard.html', {
            'is_location_admin': True,
            'location': location,
            'locations': locations,
            'templates': templates,
            'stats': {
                'total': total_passes_count,
                'done': done_count,
                'pending': pending_count,
                'today': today_count
            },
            'recent_visits': recent_visits,
        })


@login_required
@transaction.atomic
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
        quantity = int(request.POST.get('quantity', '1'))
        discount_percent = request.POST.get('discount_percent', '0')
        try:
            discount_percent = float(discount_percent)
        except ValueError:
            discount_percent = 0
        internal_notes = request.POST.get('internal_notes', '').strip()

        try:
            location = locations.get(id=loc_id)
        except Exception:
            messages.error(request, 'Invalid location selected.')
            return render(request, 'admin_panel/template_form.html', {'locations': locations})

        # Calculate price based on location price and discount
        price = float(location.price)
        if discount_percent > 0:
            price = price * (1 - (discount_percent / 100))

        # Create the Batch (PassTemplate)
        template = PassTemplate.objects.create(
            location=location,
            name=name,
            discount_percent=discount_percent,
            total_price=price,
            access_limit=quantity,
            internal_notes=internal_notes,
        )

        # Generate QR for the batch (though users will likely use individual passes)
        try:
            template.generate_qr(settings.SITE_URL)
        except Exception as e:
            pass

        # Now generate the actual passes
        from .models import PassVisit
        counter, _ = LocationPassCounter.objects.get_or_create(location=location)
        
        for i in range(quantity):
            unique_id = counter.next_id()
            pass_obj = Pass.objects.create(
                template=template,
                unique_id=unique_id,
                full_name=f"Pass {unique_id}",
                phone="N/A",
                address="Generated in bulk",
                status='ACTIVE',
            )

            # Create visits
            if location.prefix == 'COMBO':
                all_locs = Location.objects.filter(is_active=True).exclude(prefix='COMBO')
                for loc in all_locs:
                    PassVisit.objects.create(pass_obj=pass_obj, location=loc)
            else:
                PassVisit.objects.create(pass_obj=pass_obj, location=location)

            # Generate QR for each pass
            try:
                pass_obj.generate_pass_qr(settings.SITE_URL)
            except Exception:
                pass

        messages.success(request, f'Successfully generated {quantity} passes for "{template.name}".')
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
def template_delete(request, pk):
    template = get_object_or_404(PassTemplate, pk=pk)
    if not request.user.is_superuser:
        allowed = request.user.admin_locations.filter(location=template.location).exists()
        if not allowed:
            messages.error(request, 'Access denied.')
            return redirect('passes:template_list')
            
    name = template.name
    template.delete()
    messages.success(request, f'Template "{name}" deleted.')
    return redirect('passes:template_list')


@login_required
def passes_list(request):
    from apps.locations.models import Location
    from .models import PassVisit
    from django.db.models import Q
    
    visit_status = request.GET.get('visit_status', '')
    visit_date = request.GET.get('visit_date', '')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '')

    if request.user.is_superuser:
        passes = Pass.objects.select_related('template__location').all()
    else:
        location_ids = request.user.admin_locations.values_list('location_id', flat=True)
        # Show my location passes OR all COMBO passes
        passes = Pass.objects.filter(
            Q(template__location__id__in=location_ids) | 
            Q(template__location__prefix='COMBO')
        ).select_related('template__location')

        # Filter by visit status if requested (for location admins)
        if visit_status or visit_date:
            location = request.user.admin_locations.first().location
            visits = PassVisit.objects.filter(location=location)
            if visit_status:
                visits = visits.filter(status=visit_status)
            if visit_date == 'today':
                visits = visits.filter(visited_at__date=timezone.now().date())
            
            passes = passes.filter(visits__in=visits).distinct()

    if status_filter:
        passes = passes.filter(status=status_filter)
    if search:
        passes = passes.filter(unique_id__icontains=search) | passes.filter(full_name__icontains=search)

    return render(request, 'admin_panel/passes_list.html', {
        'passes': passes, 
        'status_filter': status_filter, 
        'search': search,
        'visit_status': visit_status,
        'visit_date': visit_date
    })


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
    
    # Permission check: Admin must be assigned to THIS location
    allowed = request.user.is_superuser or request.user.admin_locations.filter(location=location).exists()
    
    if not allowed:
        return render(request, 'passes/scan_visit.html', {
            'error': 'Access Denied: You are not authorized to check-in for this location.',
            'location': location,
            'pass_obj': pass_obj,
        })

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
