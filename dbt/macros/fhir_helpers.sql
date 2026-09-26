{#- Map a FHIR code system URI to the code type names Tuva uses. -#}
{% macro tuva_code_type(system_column) -%}
    case {{ system_column }}
        when 'http://snomed.info/sct' then 'snomed-ct'
        when 'http://hl7.org/fhir/sid/icd-10-cm' then 'icd-10-cm'
        when 'http://hl7.org/fhir/sid/icd-10' then 'icd-10-cm'
        when 'http://hl7.org/fhir/sid/icd-9-cm' then 'icd-9-cm'
        when 'http://www.cms.gov/Medicare/Coding/ICD10' then 'icd-10-pcs'
        when 'http://loinc.org' then 'loinc'
        when 'http://www.nlm.nih.gov/research/umls/rxnorm' then 'rxnorm'
        when 'http://hl7.org/fhir/sid/ndc' then 'ndc'
        when 'http://hl7.org/fhir/sid/cvx' then 'cvx'
        when 'http://www.ama-assn.org/go/cpt' then 'hcpcs'
        when 'https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets' then 'hcpcs'
        when 'http://www.ada.org/cdt' then 'cdt'
        else {{ system_column }}
    end
{%- endmacro %}

{#- Synthea appends digits to names ("Eliseo499") so they stay unique; strip them. -#}
{% macro clean_name(column) -%}
    nullif(trim(regexp_replace({{ column }}, '[0-9]+', '', 'g')), '')
{%- endmacro %}

{#- FHIR dateTime/instant strings → date / timestamp. Partial dates become null. -#}
{% macro fhir_date(column) -%}
    try_cast(substr({{ column }}, 1, 10) as date)
{%- endmacro %}

{% macro fhir_timestamp(column) -%}
    try_cast({{ column }} as timestamptz)::timestamp
{%- endmacro %}

{% macro ingest_datetime() -%}
    cast('{{ run_started_at.strftime("%Y-%m-%d %H:%M:%S") }}' as timestamp)
{%- endmacro %}
