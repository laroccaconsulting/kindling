select
    cast(loc.id as varchar) as location_id
  , coalesce(org.npi, cast(null as varchar)) as npi
  , cast(loc.name as varchar) as name
  , cast(null as varchar) as facility_type
  , cast(org.name as varchar) as parent_organization
  , cast(loc.address_line as varchar) as address
  , cast(loc.city as varchar) as city
  , cast(loc.state as varchar) as state
  , cast(loc.postal_code as varchar) as zip_code
  , cast(loc.latitude as float) as latitude
  , cast(loc.longitude as float) as longitude
  , {{ ingest_datetime() }} as ingest_datetime
  , '{{ var("kindling_data_source") }}' as data_source
from {{ source('fhir', 'location') }} as loc
left join {{ source('fhir', 'organization') }} as org
    on coalesce(loc.managing_organization_id, '') = org.id
    or loc.managing_organization_identifier = org.source_identifier
