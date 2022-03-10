from django.contrib import admin
from .models import Situation, Consequence, Link, ValidityPeriod


class ConsequenceInline(admin.StackedInline):
    model = Consequence
    autocomplete_fields = ['stops', 'services', 'operators']
    readonly_fields = ['data']
    show_change_link = True


class ValidityPeriodInline(admin.TabularInline):
    model = ValidityPeriod


class LinkInline(admin.TabularInline):
    model = Link


class SituationAdmin(admin.ModelAdmin):
    inlines = [ValidityPeriodInline, LinkInline, ConsequenceInline]
    list_display = ['__str__', 'reason', 'source', 'current']
    list_filter = ['reason', 'source', 'current']
    readonly_fields = ['data']


admin.site.register(Situation, SituationAdmin)
