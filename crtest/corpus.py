"""Fictional organisations and vocabulary for synthetic documents.

Every council, supplier, person and reference here is invented. Any
resemblance to a real body is coincidental. Registration numbers are
random placeholders, not real Companies House numbers.
"""

COUNCILS = [
    {"name": "Wexcombe Borough Council", "short": "WBC", "address": "Civic Centre, Market Walk, Wexcombe, WX1 2AB", "contact": "procurement@wexcombe.example.gov", "type": "sub_central"},
    {"name": "Harrowdale District Council", "short": "HDC", "address": "The Guildhall, Bridge Street, Harrowdale, HD4 7QP", "contact": "contracts@harrowdale.example.gov", "type": "sub_central"},
    {"name": "Northam Vale County Council", "short": "NVCC", "address": "County Hall, Vale Road, Northam, NV2 9TT", "contact": "commercial@northamvale.example.gov", "type": "sub_central"},
    {"name": "Stonebridge Metropolitan Borough Council", "short": "SMBC", "address": "Town Hall, Victoria Square, Stonebridge, SB1 1AA", "contact": "procurement@stonebridge.example.gov", "type": "sub_central"},
    {"name": "Eastmere and Calder District Council", "short": "ECDC", "address": "Council Offices, Calder Way, Eastmere, EM5 3LD", "contact": "tenders@eastmere-calder.example.gov", "type": "sub_central"},
    {"name": "Kingsholt City Council", "short": "KCC", "address": "Civic Hall, Cathedral Close, Kingsholt, KH1 8RF", "contact": "strategic.procurement@kingsholt.example.gov", "type": "sub_central"},
]

SUPPLIERS = [
    {"name": "Alderman Facilities Group Ltd", "reg": "09418832", "address": "Unit 4, Riverside Business Park, Wexcombe, WX3 5PL", "ta": None},
    {"name": "Brightwater Environmental Services Limited", "reg": "07720941", "address": "Brightwater House, Mill Lane, Harrowdale, HD2 4ES", "ta": "Brightwater"},
    {"name": "Cresswell Highways Ltd", "reg": "05583107", "address": "Depot Road, Northam Industrial Estate, Northam, NV4 6HW", "ta": None},
    {"name": "Dunmore Care Partnership CIC", "reg": "11204476", "address": "22 Chapel Street, Stonebridge, SB3 2CP", "ta": None},
    {"name": "Elmstead ICT Solutions Ltd", "reg": "08867310", "address": "Floor 3, Meridian Court, Kingsholt, KH2 5IT", "ta": "Elmstead Digital"},
    {"name": "Fenwick Grounds Maintenance Ltd", "reg": "06645928", "address": "The Nurseries, Fenwick Lane, Eastmere, EM2 7GM", "ta": None},
    {"name": "Greystoke Construction (Midlands) Limited", "reg": "04392218", "address": "Greystoke Yard, Canal Street, Stonebridge, SB6 1GC", "ta": None},
    {"name": "Halbrook Leisure Operations Ltd", "reg": "10931562", "address": "Halbrook Centre, Park Avenue, Wexcombe, WX7 4LO", "ta": "Halbrook Active"},
    {"name": "Ironside Waste Management Ltd", "reg": "07114290", "address": "Ironside Depot, Quarry Road, Harrowdale, HD9 1WM", "ta": None},
    {"name": "Juniper Social Care Services Ltd", "reg": "09980154", "address": "Juniper House, 8 Station Road, Northam, NV1 3JS", "ta": None},
]

SERVICES = [
    {"title": "Provision of Grounds Maintenance Services for Parks and Open Spaces", "type": "services", "cpv": ["77310000", "77311000", "77314000"], "supplier": 5},
    {"title": "Highways Reactive Maintenance and Winter Service", "type": "works", "cpv": ["45233141", "45233139", "90620000"], "supplier": 2},
    {"title": "Managed ICT Service Desk and End User Device Support", "type": "services", "cpv": ["72253000", "72500000", "50320000"], "supplier": 4},
    {"title": "Domiciliary Care Services (Lots 1-3)", "type": "services", "cpv": ["85312000", "85311100", "85000000"], "supplier": 9},
    {"title": "Household Waste and Recycling Collection Service", "type": "services", "cpv": ["90511000", "90512000", "90511200"], "supplier": 8},
    {"title": "Leisure Centre Operating Contract", "type": "services", "cpv": ["92610000", "92600000"], "supplier": 7},
    {"title": "Facilities Management for Corporate Buildings", "type": "services", "cpv": ["79993100", "50700000", "90911200"], "supplier": 0},
    {"title": "Construction of Extra Care Housing Scheme, Mill Road", "type": "works", "cpv": ["45215210", "45211000"], "supplier": 6},
    {"title": "Environmental Services Partnership (Street Cleansing)", "type": "services", "cpv": ["90610000", "90611000"], "supplier": 1},
]

KPI_LIBRARY = [
    "Jobs completed within target response time",
    "Customer satisfaction score (quarterly survey)",
    "Invoices submitted accurately and on time",
    "Health and safety incidents reported (RIDDOR)",
    "Missed collections per 100,000",
    "Service availability (monthly)",
    "First-time fix rate",
    "Staff vacancy rate",
    "Social value hours delivered",
    "Carbon emissions reported against baseline",
]

PROCEDURE_LABEL = {
    "open": "Open procedure",
    "competitive_flexible": "Competitive flexible procedure",
    "direct_award": "Direct award (section 41)",
    "framework_call_off": "Call-off from a framework",
}

GROUND_LABEL = {
    "sch8_para1_provided_for": "Schedule 8, paragraph 1 (provided for in the contract)",
    "sch8_para2_urgency": "Schedule 8, paragraph 2 (urgency and the protection of life)",
    "sch8_para3_unforeseeable": "Schedule 8, paragraph 3 (unforeseeable circumstances)",
    "sch8_para4_known_risk": "Schedule 8, paragraph 4 (materialisation of a known risk)",
    "sch8_para5_additional": "Schedule 8, paragraph 5 (additional goods, services or works)",
    "sch8_para6_restructuring": "Schedule 8, paragraph 6 (transfer on corporate restructuring)",
    "s74_non_substantial": "Section 74(1)(b) (not a substantial modification)",
    "s74_below_threshold": "Section 74(1)(c) (below-threshold modification)",
}

OFFICERS = [
    "J. Okafor, Head of Procurement",
    "M. Reilly, Strategic Commissioning Manager",
    "A. Patel, Category Manager (Place)",
    "S. Lindqvist, Senior Procurement Officer",
    "R. Hughes, Director of Resources",
]
