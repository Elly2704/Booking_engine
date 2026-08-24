from django.shortcuts import render
from django.db.models import Q, Count, Avg
from .models import Resource, ResourceCategory


def resource_list_view(request):
    resources = Resource.objects.filter(is_active=True)

    search_query = request.GET.get('q')
    if search_query:
        resources = resources.filter(
            Q(name__icontains=search_query) | Q(description__icontains=search_query)
        )

    return render(request, 'resources/resource_list.html', {'resources': resources})


def category_stats_view(request):
    categories = ResourceCategory.objects.annotate(
        total_resources=Count('resources'),
        avg_price=Avg('resources__price_per_hour')
    )

    return render(request, 'resources/category_stats.html', {'categories': categories})