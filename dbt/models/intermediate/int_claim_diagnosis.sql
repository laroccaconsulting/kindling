-- Claim diagnoses as ICD-10-CM. Synthea's EOB.diagnosis points at Condition
-- resources coded in SNOMED CT, so resolve the Condition and map SNOMED → ICD-10-CM.
-- A code already in ICD-10-CM passes through unchanged.
with dx as (
    select
        d.eob_id as claim_id
      , d.sequence
      , coalesce(
            case when d.diagnosis_system in ('http://hl7.org/fhir/sid/icd-10-cm', 'http://hl7.org/fhir/sid/icd-10')
                 then replace(d.diagnosis_code, '.', '') end
          , case when c.code_system in ('http://hl7.org/fhir/sid/icd-10-cm', 'http://hl7.org/fhir/sid/icd-10')
                 then replace(c.code_code, '.', '') end
          , map.icd10_code
        ) as icd10_code
      , d.on_admission_code
    from {{ source('fhir', 'explanation_of_benefit_diagnosis') }} as d
    left join {{ source('fhir', 'condition') }} as c
        on d.condition_id = c.id
    left join {{ ref('int_snomed_to_icd10') }} as map
        on c.code_system = 'http://snomed.info/sct'
       and c.code_code = map.snomed_code
)

select
    claim_id
  , icd10_code
  , on_admission_code
  , row_number() over (partition by claim_id order by sequence) as diagnosis_rank
from dx
where icd10_code is not null
