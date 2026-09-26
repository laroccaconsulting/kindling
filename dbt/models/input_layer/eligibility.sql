select
    cast(span.person_id as varchar) as person_id
  , cast(span.person_id as varchar) as member_id
  , cast(span.person_id as varchar) as subscriber_id
  , 'self' as subscriber_relation
  , span.enrollment_start_date
  , span.enrollment_end_date
  , cast(span.payer as varchar) as payer
  , cast(span.payer_type as varchar) as payer_type
  , cast(span.plan as varchar) as plan
  , pat.first_name
  , pat.middle_name
  , pat.last_name
  , pat.name_suffix
  , pat.social_security_number
  , pat.address
  , pat.city
  , pat.state
  , pat.zip_code
  , pat.phone
  , pat.email
  , pat.ethnicity
  , pat.sex
  , pat.race
  , pat.birth_date
  , pat.death_date
  , pat.death_flag
  , cast(null as varchar) as original_reason_entitlement_code
  , cast(null as varchar) as dual_status_code
  , cast(null as varchar) as medicare_status_code
  , cast(null as varchar) as enrollment_status
  , cast(null as integer) as hospice_flag
  , cast(null as integer) as institutional_snp_flag
  , cast(case when span.payer = 'Medicaid' then 1 else 0 end as integer) as medicaid_indicator
  , cast(null as integer) as long_term_institutional_flag
  , cast(null as varchar) as part_d_raf_type
  , cast(null as integer) as low_income_subsidy_indicator
  , cast(null as varchar) as metal_level
  , cast(null as integer) as csr_indicator
  , cast(null as integer) as enrollment_duration_months
  , cast(null as integer) as esrd_status
  , cast(null as integer) as transplant_duration_months
  , cast(null as varchar) as group_id
  , cast(null as varchar) as group_name
  , 'fhir:ExplanationOfBenefit' as file_name
  , cast(null as date) as file_date
  , {{ ingest_datetime() }} as ingest_datetime
  , '{{ var("kindling_data_source") }}' as data_source
from {{ ref('int_eligibility_span') }} as span
inner join {{ ref('patient') }} as pat
    on span.person_id = pat.person_id
