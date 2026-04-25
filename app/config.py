# ============= FIELDS =============
UID = "uid"
UPDATE = "updatedAt"
TITLE = "title_fr"
DESC = "description_fr"
LONG_DESC = "longdescription_fr"
LOC_NAME = "location_name"
LOC_DEPT = "location_department"
LOC_CITY = "location_city"
LOC_REGION = "location_region"
LOC_ADDRESS = "location_address"
CONDITIONS = "conditions_fr"
URL = "canonicalurl"
LOC_COORD = "location_coordinates"
LOC_LAT = "location_lat"
LOC_LON = "location_lon"
TIMINGS = "timings"
FIRST_DATE = "first_date"

# Fields from OpenAgenda to be concatenated for the embedding
VECTORIZED_FIELDS = [TITLE, DESC, LONG_DESC, CONDITIONS, LOC_NAME, LOC_CITY, LOC_ADDRESS, LOC_DEPT, LOC_REGION]

# Fields to be kept as metadata for filtering (Azure AI Search / OData)
METADATA_FIELDS = [UID, UPDATE, TITLE, DESC, LONG_DESC, LOC_NAME, LOC_DEPT, LOC_CITY, LOC_REGION, LOC_ADDRESS, CONDITIONS, URL, TIMINGS, LOC_COORD ]
