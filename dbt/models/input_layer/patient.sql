select
    cast(id as varchar) as person_id
  , cast(id as varchar) as patient_id
  , {{ clean_name('given_name') }} as first_name
  , {{ clean_name('middle_name') }} as middle_name
  , {{ clean_name('family_name') }} as last_name
  , cast(name_suffix as varchar) as name_suffix
  , case gender when 'male' then 'male' when 'female' then 'female' else 'unknown' end as sex
  , case race_code
        when '2106-3' then 'white'
        when '2054-5' then 'black or african american'
        when '2028-9' then 'asian'
        when '1002-5' then 'american indian or alaska native'
        when '2076-8' then 'native hawaiian or other pacific islander'
        when '2131-1' then 'other race'
        else 'unknown'
    end as race
  , case ethnicity_code
        when '2135-2' then 'Hispanic or Latino'
        when '2186-5' then 'Not Hispanic or Latino'
        else 'unknown'
    end as ethnicity
  , {{ fhir_date('birth_date') }} as birth_date
  , {{ fhir_date('deceased_datetime') }} as death_date
  , cast(case when deceased_flag then 1 else 0 end as integer) as death_flag
  , cast(ssn as varchar) as social_security_number
  , cast(address_line as varchar) as address
  , cast(city as varchar) as city
  , cast(state as varchar) as state
  , cast(postal_code as varchar) as zip_code
  , cast(null as varchar) as county
  , cast(latitude as float) as latitude
  , cast(longitude as float) as longitude
  , cast(phone as varchar) as phone
  , cast(email as varchar) as email
  , {{ ingest_datetime() }} as ingest_datetime
  , '{{ var("kindling_data_source") }}' as data_source
from {{ source('fhir', 'patient') }}
