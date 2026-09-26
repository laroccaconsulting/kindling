-- One representative NDC per RxNorm concept, from Tuva's CodeRx package table.
-- Synthea prescribes by RxNorm (clinical or branded drug); pharmacy claims and
-- Tuva's adherence measures key on NDC. Prefer active packages, then the lowest NDC,
-- so the choice is stable across runs.
with packages as (
    select
        cast(drug_id as varchar) as rxnorm_code
      , ndc11
      , active
    from {{ ref('the_tuva_project', 'terminology__coderx_packages') }}
    union all
    select
        cast(clinical_drug_id as varchar) as rxnorm_code
      , ndc11
      , active
    from {{ ref('the_tuva_project', 'terminology__coderx_packages') }}
)

, ranked as (
    select
        rxnorm_code
      , lpad(cast(ndc11 as varchar), 11, '0') as ndc_code
      , row_number() over (
            partition by rxnorm_code
            order by case when cast(active as varchar) in ('true', 'True', '1') then 0 else 1 end, ndc11
        ) as rn
    from packages
    where ndc11 is not null
)

select rxnorm_code, ndc_code
from ranked
where rn = 1
