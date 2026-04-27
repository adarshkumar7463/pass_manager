from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.text import slugify
from .models import Location, AdminLocation


@login_required
def location_list(request):
    if request.user.is_superuser:
        locations = Location.objects.all()
    else:
        location_ids = request.user.admin_locations.values_list('location_id', flat=True)
        locations = Location.objects.filter(id__in=location_ids)
    return render(request, 'admin_panel/locations.html', {'locations': locations})


@login_required
def location_create(request):
    if not request.user.is_superuser:
        messages.error(request, 'Only superadmins can create locations.')
        return redirect('passes:dashboard')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        address = request.POST.get('address', '').strip()
        prefix = request.POST.get('prefix', '').strip().upper()
        price = request.POST.get('price', '0.00')
        image = request.FILES.get('image')

        if not name or not prefix:
            messages.error(request, 'Name and prefix are required.')
        elif Location.objects.filter(prefix=prefix).exists():
            messages.error(request, f'Prefix "{prefix}" already in use.')
        else:
            slug = slugify(name)
            base_slug = slug
            counter = 1
            while Location.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            loc = Location.objects.create(
                name=name, slug=slug, description=description,
                address=address, prefix=prefix, price=price,
                image=image if image else None
            )
            messages.success(request, f'Location "{loc.name}" created successfully.')
            return redirect('passes:dashboard')

    return render(request, 'admin_panel/location_form.html')


@login_required
def location_edit(request, pk):
    if not request.user.is_superuser:
        messages.error(request, 'Only superadmins can edit locations.')
        return redirect('passes:dashboard')

    location = get_object_or_404(Location, pk=pk)
    if request.method == 'POST':
        location.name = request.POST.get('name', location.name).strip()
        location.description = request.POST.get('description', location.description).strip()
        location.address = request.POST.get('address', location.address).strip()
        location.price = request.POST.get('price', location.price)
        if request.FILES.get('image'):
            location.image = request.FILES['image']
        location.save()
        messages.success(request, 'Location updated.')
        return redirect('passes:dashboard')

    return render(request, 'admin_panel/location_form.html', {'location': location})


@login_required
def location_delete(request, pk):
    if not request.user.is_superuser:
        messages.error(request, 'Only superadmins can delete locations.')
        return redirect('passes:dashboard')
    
    location = get_object_or_404(Location, pk=pk)
    name = location.name
    location.delete()
    messages.success(request, f'Location "{name}" deleted.')
    return redirect('passes:dashboard')
