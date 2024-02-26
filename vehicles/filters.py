from django.db.models import Q
from django_filters.rest_framework import (
    BooleanFilter,
    CharFilter,
    ChoiceFilter,
    FilterSet,
    ModelChoiceFilter,
    NumberFilter,
)
from sql_util.utils import Exists, SubqueryCount

from busstops.models import Operator


def filter_not_empty(queryset, name, value):
    condition = Q(**{name: ""})
    if value:
        condition = ~condition
    return queryset.filter(condition)


class VehicleEditFilter(FilterSet):
    change = ChoiceFilter(
        method="change_filter",
        label="Change",
        choices=(
            ("reg", "Number plate"),
            ("vehicle_type", "Type"),
            ("name", "Name"),
            ("notes", "Notes"),
            ("branding", "Branding"),
            ("withdrawn", "Withdrawn"),
            ("livery", "Livery"),
            ("previous_reg", "Previous reg"),
            ("features", "Features"),
        ),
    )
    vehicle_id = NumberFilter(label="Vehicle ID")
    user = NumberFilter(label="User ID")
    vehicle__operator = ModelChoiceFilter(
        label="Operator",
        queryset=Operator.objects.filter(
            # yes it might seem nicer to filter by 'count__gt=0' instead, but this is faster
            Exists("vehicle__vehicleedit", filter=Q(approved=None))
        )
        .annotate(count=SubqueryCount("vehicle__vehicleedit", filter=Q(approved=None)))
        .order_by("-count")
        .only("name"),
    )
    vehicle__withdrawn = BooleanFilter(label="Withdrawn")
    url = BooleanFilter(label="URL", method=filter_not_empty)
    livery = NumberFilter()
    pending = BooleanFilter(label="Pending", method="pending_filter", required=True)

    def __init__(self, *args, **kwargs):
        super(FilterSet, self).__init__(*args, **kwargs)

        self.filters[
            "vehicle__operator"
        ].field.label_from_instance = lambda o: f"{o} ({o.count})"

    def change_filter(self, queryset, name, value):
        if value == "livery":
            return queryset.filter(~Q(livery=None) | ~Q(colours=""))
        if value == "previous_reg":
            return queryset.filter(Q(**{"changes__Previous reg__isnull": False}))
        if value == "features":
            return queryset.filter(Exists("features"))
        return queryset.filter(~Q(**{value: ""}))

    def pending_filter(self, queryset, name, value):
        return queryset.filter(approved__isnull=value)


class VehicleRevisionFilter(FilterSet):
    vehicle__operator = CharFilter(
        label="Operator ID",
    )
    vehicle = NumberFilter(label="Vehicle ID")
    user = NumberFilter(label="User ID")
