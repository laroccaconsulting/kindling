-- Pharmacy claims from ExplanationOfBenefit (type = pharmacy). Synthea prescribes by
-- RxNorm, so each line gets a representative NDC; days supply defaults to
-- var('kindling_default_days_supply') because Synthea doesn't record it.
select
    cast(c.claim_id as varchar) as claim_id
  , cast(i.sequence as integer) as claim_line_number
  , cast(c.person_id as varchar) as person_id
  , cast(c.person_id as varchar) as member_id
  , cast(c.payer as varchar) as payer
  , cast(c.plan as varchar) as plan
  , cast(c.rendering_npi as varchar) as prescribing_provider_npi
  , cast(null as varchar) as dispensing_provider_npi
  , {{ fhir_date('i.service_start') }} as dispensing_date
  , ndc.ndc_code
  , cast(coalesce(i.quantity, {{ var('kindling_default_days_supply') }}) as integer) as quantity
  , cast({{ var('kindling_default_days_supply') }} as integer) as days_supply
  , cast(0 as integer) as refills
  , c.paid_date
  , cast(coalesce(i.paid_amount, c.payment_amount, 0) as float) as paid_amount
  , cast(coalesce(i.allowed_amount, c.total_submitted, 0) as float) as allowed_amount
  , cast(coalesce(i.submitted_amount, i.net_amount, c.total_submitted, 0) as float) as charge_amount
  , cast(i.coinsurance_amount as float) as coinsurance_amount
  , cast(null as float) as copayment_amount
  , cast(i.deductible_amount as float) as deductible_amount
  , cast(1 as integer) as in_network_flag
  , 'fhir:ExplanationOfBenefit' as file_name
  , cast(null as date) as file_date
  , {{ ingest_datetime() }} as ingest_datetime
  , '{{ var("kindling_data_source") }}' as data_source
from {{ ref('int_claim') }} as c
inner join {{ source('fhir', 'explanation_of_benefit_item') }} as i
    on c.claim_id = i.eob_id
left join {{ ref('int_rxnorm_to_ndc') }} as ndc
    on i.product_system = 'http://www.nlm.nih.gov/research/umls/rxnorm'
   and i.product_code = ndc.rxnorm_code
where c.claim_type = 'pharmacy'
