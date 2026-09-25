with role as (
    select
        practitioner_npi
      , any_value(specialty_display) as specialty
      , any_value(organization_name) as practice_affiliation
    from {{ source('fhir', 'practitioner_role') }}
    group by practitioner_npi
)

select
    cast(p.id as varchar) as practitioner_id
  , cast(p.npi as varchar) as npi
  , {{ clean_name('p.given_name') }} as first_name
  , {{ clean_name('p.family_name') }} as last_name
  , cast(role.practice_affiliation as varchar) as practice_affiliation
  , lower(cast(role.specialty as varchar)) as specialty
  , cast(null as varchar) as sub_specialty
  , {{ ingest_datetime() }} as ingest_datetime
  , '{{ var("kindling_data_source") }}' as data_source
from {{ source('fhir', 'practitioner') }} as p
left join role
    on p.npi = role.practitioner_npi
