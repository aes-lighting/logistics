"""Map JSON stores/code constants -> ontology classes for AES Logistics.

JSON-driven domain (no SQL). The two stores in server/ are the "tables":
  - schedule_store.json   -> aesl:Delivery  (+ nested LineItem, DeliveryTicket, Geotag)
  - inventory_store.json  -> aesl:InventoryEntry (+ nested LocationSlit)
Plus a job->pm directory -> aesl:JobDirectoryEntry.

Kept as ONE curated map used by extract_schema_snapshot.py / generate_ontology.py.
"""

# Store key -> output class. Absent stores => coverage error.
STORE_TO_CLASS = {
    "deliveries": "Delivery",
    "settings": None,  # {ics_url} is not a business entity; carry as delivery-level edge only
    "entries": "InventoryEntry",
    "job_pm_directory": "JobDirectoryEntry",
}

# Business entity classes, keyed by their record id key (used for coverage).
ENTITY_TO_CLASS = {
    "delivery": "Delivery",
    "inventory_entry": "InventoryEntry",
    "job_directory": "JobDirectoryEntry",
    "calendar_event": "CalendarEvent",
    "delivery_ticket": "DeliveryTicket",
    "line_item": "LineItem",
    "location_slit": "LocationSlit",
    "geotag": "Geotag",
}

# Nested value objects that are NOT store entities but project to classes.
VALUE_OBJECTS = ("LineItem", "LocationSlit", "Geotag")

# Order for deterministic emission.
CLASS_ORDER = [
    "Delivery", "InventoryEntry", "JobDirectoryEntry", "CalendarEvent",
    "DeliveryTicket", "LineItem", "LocationSlit", "Geotag",
]


def classes_for_generation() -> list[str]:
    return [c for c in CLASS_ORDER if c in ENTITY_TO_CLASS.values() or c in VALUE_OBJECTS]