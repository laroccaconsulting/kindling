-- One ICD-10-CM code per SNOMED CT concept, from the NLM SNOMED CT → ICD-10-CM map
-- that ships with Tuva's terminology.
--
-- The map is rule-based (age, sex, co-occurring conditions). Claims need a single
-- code, so we take the first unconditional target: lowest map group, then priority,
-- where the rule is TRUE / OTHERWISE TRUE and a target exists. That's what a coder
-- would pick without extra context. Conditional targets are ignored.
with candidates as (
    select
        cast(referenced_component_id as varchar) as snomed_code
      , replace(map_target, '.', '') as icd10_code
      , map_target_name as icd10_description
      , row_number() over (
            partition by referenced_component_id
            order by cast(map_group as integer), cast(map_priority as integer)
        ) as rn
    from {{ ref('the_tuva_project', 'terminology__snomed_icd_10_map') }}
    where cast(active as varchar) in ('1', 'true', 'True')
      and map_target is not null
      and map_target <> ''
      and upper(map_rule) in ('TRUE', 'OTHERWISE TRUE')
)

select snomed_code, icd10_code, icd10_description
from candidates
where rn = 1
