-- Professional and institutional claim lines from ExplanationOfBenefit.
--
-- Synthea gaps, and how this model fills them (documented in docs/guides):
--   * diagnoses are SNOMED Conditions   → ICD-10-CM via int_snomed_to_icd10
--   * services are SNOMED/LOINC/CVX      → hcpcs_code only when the line is CPT/HCPCS
--   * place of service reflects facility → derived from Encounter.class (stg_encounter)
--   * no bill type / revenue codes       → derived from the encounter setting
{%- set n = 25 %}

with lines as (
    select
        i.eob_id as claim_id
      , i.sequence as claim_line_number
      , {{ fhir_date('i.service_start') }} as claim_line_start_date
      , coalesce({{ fhir_date('i.service_end') }}, {{ fhir_date('i.service_start') }}) as claim_line_end_date
      , case when i.product_system in ('http://www.ama-assn.org/go/cpt', 'https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets')
             then i.product_code end as hcpcs_code
      , i.quantity
      , i.paid_amount
      , i.allowed_amount
      , coalesce(i.submitted_amount, i.net_amount) as charge_amount
      , i.coinsurance_amount
      , i.deductible_amount
    from {{ source('fhir', 'explanation_of_benefit_item') }} as i
    where i.claim_type in ('professional', 'institutional')
)

, dx as (
    select
        claim_id
        {%- for k in range(1, n + 1) %}
      , max(case when diagnosis_rank = {{ k }} then icd10_code end) as diagnosis_code_{{ k }}
      , max(case when diagnosis_rank = {{ k }} then on_admission_code end) as diagnosis_poa_{{ k }}
        {%- endfor %}
    from {{ ref('int_claim_diagnosis') }}
    group by claim_id
)

select
    cast(c.claim_id as varchar) as claim_id
  , cast(l.claim_line_number as integer) as claim_line_number
  , c.claim_type
  , cast(c.person_id as varchar) as person_id
  , cast(c.person_id as varchar) as member_id
  , cast(c.payer as varchar) as payer
  , cast(c.plan as varchar) as plan
  , c.claim_start_date
  , c.claim_end_date
  , l.claim_line_start_date
  , l.claim_line_end_date
  , case when c.claim_type = 'institutional' and c.class_code = 'IMP' then c.encounter_start_date end as admission_date
  , case when c.claim_type = 'institutional' and c.class_code = 'IMP' then c.encounter_end_date end as discharge_date
  , cast(null as varchar) as admit_source_code
  , cast(null as varchar) as admit_type_code
  , case when c.claim_type = 'institutional' and c.class_code = 'IMP'
         then coalesce(c.discharge_disposition_code, '01') end as discharge_disposition_code
  , case when c.claim_type = 'professional' then c.place_of_service_code end as place_of_service_code
  , case when c.claim_type = 'institutional' then c.bill_type_code end as bill_type_code
  , cast(null as varchar) as drg_code_type
  , cast(null as varchar) as drg_code
  , case when c.claim_type = 'institutional' then c.revenue_center_code end as revenue_center_code
  , cast(l.quantity as double) as service_unit_quantity
  , l.hcpcs_code
  , cast(null as varchar) as hcpcs_modifier_1
  , cast(null as varchar) as hcpcs_modifier_2
  , cast(null as varchar) as hcpcs_modifier_3
  , cast(null as varchar) as hcpcs_modifier_4
  , cast(null as varchar) as hcpcs_modifier_5
  , cast(c.rendering_npi as varchar) as rendering_npi
  , cast(null as varchar) as rendering_tin
  , cast(c.rendering_npi as varchar) as billing_npi
  , cast(null as varchar) as billing_tin
  , cast(null as varchar) as facility_npi
  , c.paid_date
  , cast(coalesce(l.paid_amount, 0) as float) as paid_amount
  , cast(coalesce(l.allowed_amount, 0) as float) as allowed_amount
  , cast(coalesce(l.charge_amount, 0) as float) as charge_amount
  , cast(l.coinsurance_amount as float) as coinsurance_amount
  , cast(null as float) as copayment_amount
  , cast(l.deductible_amount as float) as deductible_amount
  , cast(coalesce(l.allowed_amount, 0) as float) as total_cost_amount
  , case when dx.claim_id is not null then 'icd-10-cm' end as diagnosis_code_type
    {%- for k in range(1, n + 1) %}
  , dx.diagnosis_code_{{ k }}
    {%- endfor %}
    {%- for k in range(1, n + 1) %}
  , dx.diagnosis_poa_{{ k }}
    {%- endfor %}
  , cast(null as varchar) as procedure_code_type
    {%- for k in range(1, n + 1) %}
  , cast(null as varchar) as procedure_code_{{ k }}
    {%- endfor %}
    {%- for k in range(1, n + 1) %}
  , cast(null as date) as procedure_date_{{ k }}
    {%- endfor %}
  , cast(1 as integer) as in_network_flag
  , 'fhir:ExplanationOfBenefit' as file_name
  , cast(null as date) as file_date
  , {{ ingest_datetime() }} as ingest_datetime
  , '{{ var("kindling_data_source") }}' as data_source
from {{ ref('int_claim') }} as c
inner join lines as l
    on c.claim_id = l.claim_id
left join dx
    on c.claim_id = dx.claim_id
where c.claim_type in ('professional', 'institutional')
