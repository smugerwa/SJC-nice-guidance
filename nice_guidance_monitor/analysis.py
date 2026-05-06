from __future__ import annotations

import json
import os
import re
from textwrap import dedent


def analyse_item(item: dict, config: dict) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return fallback_analysis(item, config)

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    max_chars = int(config.get("llm", {}).get("max_source_chars_per_item", 45000))
    source_text = "\n\n".join(
        f"SOURCE: {page.get('url')}\n{page.get('text', '')}"
        for page in item.get("source_pages", [])
    )[:max_chars]

    prompt = dedent(f"""
    You are creating an internal UK primary care clinical governance report from NICE source material.
    Use only the supplied NICE source text. Do not invent dates, recommendations or actions.
    Distinguish mandatory action from suggested local good practice. Do not give individual patient advice.

    Return strict JSON with these keys:
    included boolean;
    exclusion_reason string;
    guidance_identification object;
    clinical_brief object with what_changed string, key_takeaways array of 3 to 6 concise clinician-facing bullet strings, practice_implication string, meeting_discussion string, suggested_action string, source_basis string. This is the main report output. It must be concise, specific, and focused on what clinicians should know or change in practice. If the monthly update is administrative only, say that clearly, then give standing clinical takeaways only if the guidance is highly relevant to primary care;
    plain_english_summary array of 5 to 8 strings;
    key_clinical_points array of concise clinically specific strings. This is mandatory for included items and must include exact thresholds, symptom clusters, timelines, prescribing criteria or referral triggers when present in the NICE source. For example, do not summarise ovarian cancer guidance without listing the persistent symptom set and CA125 age thresholds if those appear in the source;
    key_clinical_points_by_heading array of objects with heading, source_url, points. Create one object for every NICE source page/chapter/major heading that contains clinically or operationally relevant content. Do not only extract the overview. Include recommendation numbers, definitions, tables, criteria, timeframes, restrictions, monitoring, implementation caveats, and primary care interface points where present;
    key_findings object with arrays new_recommendations, updated_recommendations, may_change_practice_behaviour, unlikely_to_affect_primary_care;
    relevance object with score integer 0-5, rationale string, staff_groups array;
    required_actions array of objects with classification, owner, deadline, priority, reason, meeting_note_wording;
    impact_assessment object with clinical, operational, prescribing, referral_pathway, patient_communication, governance_cqc, financial_resource;
    recommended_communication object with gp_meeting, nurse_pharmacist_update, admin_care_navigation_update;
    source_urls array;
    source_incomplete boolean.

    Strict primary-care inclusion rule:
    Include an item in the main report only if it creates a concrete UK primary care action or decision, such as a GP/nurse/pharmacist prescribing change, monitoring requirement, referral/pathway change, diagnostic threshold, safety-netting advice, patient communication change, care-navigation instruction, template/SOP update, audit or staff briefing.
    Do not include specialist-only cancer drugs, tertiary procedures, hospital-only treatments, or NHS commissioning/funding mandates in the main report just because they are NICE guidance. Put them in the appendix unless the source gives a specific primary care action beyond awareness/referral onward.
    Do not classify NHS England funding requirements as GP practice actions.

    Item metadata:
    {json.dumps(item, ensure_ascii=False)[:5000]}

    NICE source material:
    {source_text}
    """)
    response = client.chat.completions.create(
        model=config.get("llm", {}).get("model", "gpt-4.1"),
        temperature=config.get("llm", {}).get("temperature", 0.1),
        messages=[
            {"role": "system", "content": "You produce cautious, evidence-grounded UK clinical governance analysis."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    result = json.loads(response.choices[0].message.content)
    if not result.get("clinical_brief"):
        result["clinical_brief"] = _clinical_brief_from_source(item, source_text)
    if not result.get("key_clinical_points"):
        result["key_clinical_points"] = _clinical_points_from_source(item, source_text)
    if not result.get("key_clinical_points_by_heading"):
        result["key_clinical_points_by_heading"] = _clinical_points_by_heading_from_source(item)
    result["raw_item"] = item
    result = _apply_primary_care_gate(result, item)
    return result


def fallback_analysis(item: dict, config: dict) -> dict:
    title = item.get("title", "")
    ref = item.get("reference", "")
    status = item.get("status", "other")
    text = "\n".join(page.get("text", "") for page in item.get("source_pages", []))
    lower = f"{title} {text}".lower()
    key_clinical_points = _clinical_points_from_source(item, text)
    key_clinical_points_by_heading = _clinical_points_by_heading_from_source(item)
    clinical_brief = _clinical_brief_from_source(item, text)

    score = 1
    included = True
    reason = "Specialist-led item with limited direct primary care interface."
    staff = ["GP"]
    actions = [{
        "classification": "Awareness only",
        "owner": "Clinical governance lead",
        "deadline": "Next monthly governance review",
        "priority": "low",
        "reason": "Review for awareness; no clear practice-level change identified by heuristic analysis.",
        "meeting_note_wording": f"{ref}: noted for awareness; no protocol change proposed pending clinician review.",
    }]

    primary_care_terms = (
        "primary care", "gp", "general practice", "menopause", "hrt",
        "suspected cancer", "ovarian cancer", "acne", "hyperkalaemia",
        "spirometry", "copd", "asthma", "low back pain", "self-management",
    )
    specialist_or_low_interface_terms = (
        "multiple myeloma", "astrocytoma", "oligodendroglioma",
        "gastrointestinal stromal tumours", "squamous cell carcinoma",
    )

    if ref == "CG122":
        included = False
        score = 0
        reason = "Duplicate/legacy ovarian cancer guidance; primary care action is captured under NG12 and QS18."
        actions = []
    elif ref in {"NG12", "QS18", "HTG776"}:
        score = 5 if ref in {"NG12", "HTG776"} else 4
        reason = "Primary-care-facing guidance likely to affect recognition, investigation, referral, diagnostics or local SOPs."
        staff = ["GP", "nurse", "pharmacist", "practice manager", "care navigation"]
    elif ref in {"NG23", "NG198"}:
        score = 4
        reason = "Common primary care presentation or prescribing area; likely to affect routine clinical advice or treatment choices."
        staff = ["GP", "nurse", "pharmacist"]
    elif ref in {"TA1148", "HTG712"}:
        score = 3
        reason = "Moderate primary care interface through prescribing, monitoring, patient advice or pathway awareness."
        staff = ["GP", "pharmacist", "nurse"]
    elif ref == "HTG777":
        included = False
        score = 0
        reason = "Specialist interventional procedure with limited routine primary care practice change; awareness only."
        actions = []
    elif ref == "TA1144" or "terminated appraisal" in lower or "unable to make a recommendation" in lower:
        included = False
        score = 0
        reason = "Terminated appraisal or no NICE recommendation; no actionable clinical recommendation for primary care."
        actions = []
    elif any(term in lower for term in specialist_or_low_interface_terms) and ref != "TA1148":
        included = False
        score = 0
        reason = "Specialist-led guidance with no clear routine primary care practice change."
        actions = []
    elif "suspected cancer" in lower or "ovarian cancer" in lower or "spirometry" in lower:
        score = 5 if ("suspected cancer" in lower or "spirometry" in lower) else 4
        reason = "Primary-care-facing guidance likely to affect recognition, investigation, referral, diagnostics or local SOPs."
        staff = ["GP", "nurse", "pharmacist", "practice manager", "care navigation"]
    elif "menopause" in lower or "hrt" in lower or "acne" in lower:
        score = 4
        reason = "Common primary care presentation or prescribing area; likely to affect routine clinical advice or treatment choices."
        staff = ["GP", "nurse", "pharmacist"]
    elif "hyperkalaemia" in lower or "low back pain" in lower:
        score = 3
        reason = "Moderate primary care interface through prescribing, monitoring, patient advice or referral pathway awareness."
        staff = ["GP", "pharmacist", "nurse"]
    elif any(term in lower for term in primary_care_terms):
        score = 3
        reason = "Potential primary care impact through recognition, investigation, prescribing, monitoring or patient advice."
        staff = ["GP", "nurse", "pharmacist", "practice manager"]

    if included and score >= 3:
        actions = [{
            "classification": "Share with relevant clinicians",
            "owner": "Clinical governance lead",
            "deadline": "Before next clinical meeting",
            "priority": "medium",
            "reason": "Potential primary care workflow impact; confirm against full NICE recommendations.",
            "meeting_note_wording": f"{ref}: review NICE update and confirm whether local protocol, prescribing or referral pathway changes are needed.",
        }]
    result = {
        "included": included,
        "exclusion_reason": "" if included else reason,
        "guidance_identification": {
            "title": title,
            "nice_reference": ref,
            "guidance_type": item.get("guidance_type", ""),
            "publication_or_update_date": item.get("last_updated") or item.get("published", ""),
            "url": item.get("url", ""),
            "status": status,
        },
        "plain_english_summary": [
            clinical_brief["what_changed"],
            clinical_brief["practice_implication"],
            clinical_brief["meeting_discussion"],
        ],
        "clinical_brief": clinical_brief,
        "key_clinical_points": key_clinical_points,
        "key_clinical_points_by_heading": key_clinical_points_by_heading,
        "key_findings": {
            "new_recommendations": [],
            "updated_recommendations": [],
            "may_change_practice_behaviour": [],
            "unlikely_to_affect_primary_care": [],
        },
        "relevance": {"score": score, "rationale": reason, "staff_groups": staff},
        "required_actions": actions,
        "impact_assessment": {
            "clinical": reason,
            "operational": "To be confirmed by clinician review.",
            "prescribing": "To be confirmed by clinician review.",
            "referral_pathway": "To be confirmed by clinician review.",
            "patient_communication": "To be confirmed by clinician review.",
            "governance_cqc": "Keep source log and decision record.",
            "financial_resource": "To be confirmed locally.",
        },
        "recommended_communication": {
            "gp_meeting": actions[0]["meeting_note_wording"] if actions else "",
            "nurse_pharmacist_update": "",
            "admin_care_navigation_update": "",
        },
        "source_urls": [page.get("url") for page in item.get("source_pages", [])] or [item.get("url", "")],
        "source_incomplete": item.get("source_incomplete", False),
        "raw_item": item,
    }
    return _apply_primary_care_gate(result, item)


def _apply_primary_care_gate(result: dict, item: dict) -> dict:
    """Keep the visible report tightly focused on primary care action.

    The LLM can over-weight legal/NHS funding language in specialist NICE
    appraisals. This deterministic pass prevents specialist-only items from
    appearing in the main meeting brief unless there is a concrete GP practice
    interface.
    """
    ident = result.setdefault("guidance_identification", {})
    title = ident.get("title") or item.get("title", "")
    ref = ident.get("nice_reference") or item.get("reference", "")
    guidance_type = (ident.get("guidance_type") or item.get("guidance_type", "")).lower()
    haystack = " ".join([
        title,
        ref,
        guidance_type,
        result.get("clinical_brief", {}).get("what_changed", ""),
        result.get("clinical_brief", {}).get("practice_implication", ""),
        " ".join(result.get("clinical_brief", {}).get("key_takeaways", []) or []),
        " ".join(result.get("key_clinical_points", []) or []),
    ]).lower()

    def exclude(reason: str, score: int = 1) -> dict:
        result["included"] = False
        result["exclusion_reason"] = reason
        result.setdefault("relevance", {})["score"] = min(int(result.get("relevance", {}).get("score", score) or score), score)
        result.setdefault("relevance", {})["rationale"] = reason
        result["required_actions"] = []
        result["recommended_communication"] = {
            "gp_meeting": "",
            "nurse_pharmacist_update": "",
            "admin_care_navigation_update": "",
        }
        return result

    explicit_include_refs = {"NG12", "NG23", "NG198", "QS18", "HTG712", "HTG776", "TA1148"}
    explicit_exclude_refs = {"TA1144", "TA1145", "TA1146", "TA1147", "TA1149", "HTG777", "CG122"}
    if ref in explicit_include_refs:
        return result
    if ref in explicit_exclude_refs:
        if ref == "CG122":
            return exclude("Duplicate or legacy ovarian cancer guidance; primary care action is captured under NG12 and QS18.", 0)
        if ref == "TA1144":
            return exclude("Terminated appraisal or no actionable NICE recommendation for routine primary care.", 0)
        return exclude("Specialist-led guidance with no concrete routine UK primary care practice action.", 1)

    specialist_terms = (
        "multiple myeloma", "astrocytoma", "oligodendroglioma", "glioma",
        "gastrointestinal stromal tumour", "gastrointestinal stromal tumor",
        "head and neck squamous cell carcinoma", "squamous cell carcinoma",
        "advanced cancer", "metastatic", "neoadjuvant", "adjuvant",
        "chemotherapy", "immunotherapy", "kinase inhibitor", "bortezomib",
        "pembrolizumab", "ripretinib", "vorasidenib", "belantamab",
        "embolisation", "intracranial", "cerebrospinal fluid",
    )
    primary_care_action_terms = (
        "primary care", "general practice", "gp", "community pharmacy",
        "prescribing", "prescribe", "monitor", "blood test", "serum",
        "referral criteria", "suspected cancer", "safety-net", "safety net",
        "diagnostic threshold", "direct-access", "template", "sop",
        "patient advice", "care navigation", "review at", "formulary",
        "shared care", "ca125", "ultrasound", "hrt", "acne", "menopause",
        "spirometry", "asthma", "copd", "hyperkalaemia", "low back pain",
    )
    funding_only_terms = (
        "nhs england is required to fund",
        "must fund",
        "within 90 days",
        "commissioners",
        "funding mandate",
        "legal requirement to fund",
    )

    has_specialist_signal = any(term in haystack for term in specialist_terms)
    has_primary_care_action = any(term in haystack for term in primary_care_action_terms)
    has_funding_only_signal = any(term in haystack for term in funding_only_terms)

    if "technology appraisal" in guidance_type and has_specialist_signal:
        return exclude("Specialist technology appraisal with no concrete routine primary care action; listed for awareness only.", 1)
    if "interventional" in guidance_type and not has_primary_care_action:
        return exclude("Specialist interventional procedure guidance with no routine primary care practice change.", 1)
    if has_funding_only_signal and not has_primary_care_action:
        return exclude("NHS commissioning/funding requirement only; no concrete GP practice action identified.", 1)

    score = int(result.get("relevance", {}).get("score", 0) or 0)
    include_min = 3
    if score < include_min:
        return exclude(result.get("exclusion_reason") or "Low primary care relevance; awareness only.", score)

    return result


def _clinical_points_from_source(item: dict, text: str) -> list[str]:
    title = item.get("title", "")
    ref = item.get("reference", "")
    lower = f"{title} {ref} {text}".lower()
    points: list[str] = []

    if "ovarian cancer" in lower or ref in {"NG12", "QS18", "CG122"}:
        points.extend([
            "Persistent symptoms suggesting ovarian cancer include abdominal distension/bloating, early satiety or loss of appetite, pelvic or abdominal pain, and increased urinary urgency and/or frequency, particularly when persistent/frequent and especially in people aged 50 or over.",
            "Also consider ovarian cancer testing for unexplained weight loss, unexplained fatigue, unexplained changes in bowel habit, or symptoms suggesting IBS for the first time in people aged 50 or over.",
            "For people aged 39 or under with persistent symptoms suggesting ovarian cancer, CA125 should not be used in isolation; consider urgent direct-access ultrasound of the abdomen and pelvis.",
            "For people aged 40 or over with persistent symptoms suggesting ovarian cancer, measure CA125 in primary care.",
            "Urgent direct-access ultrasound thresholds by age and CA125: 40-49 years 35 IU/ml or greater; 50-59 years 31 IU/ml or greater; 60-69 years 24 IU/ml or greater; 70-79 years 25 IU/ml or greater; 80+ years 31 IU/ml or greater.",
            "Urgent direct-access ultrasound means ultrasound within 2 weeks, with primary care retaining clinical responsibility including acting on the result.",
            "If ultrasound suggests ovarian cancer, refer using the suspected cancer pathway; if CA125 is below threshold or ultrasound is normal, investigate other causes and safety-net return if symptoms become more frequent or persistent.",
        ])

    if ref == "NG198" or "acne vulgaris" in lower:
        points.extend([
            "First-line treatment is a 12-week course selected by acne severity, patient preference, and discussion of advantages and disadvantages.",
            "NICE first-line options include fixed topical adapalene with benzoyl peroxide for any acne severity; fixed topical tretinoin with clindamycin for any acne severity; and fixed topical benzoyl peroxide with clindamycin for mild to moderate acne.",
            "For moderate to severe acne, NICE options include fixed topical adapalene with benzoyl peroxide plus oral lymecycline or oral doxycycline, or topical azelaic acid plus oral lymecycline or oral doxycycline.",
            "Review first-line treatment at 12 weeks, checking response and side effects.",
            "If an oral antibiotic is used and acne has improved but not cleared, consider continuing the antibiotic with topical treatment for up to 12 more weeks.",
            "Only continue antibiotic-containing treatment beyond 6 months in exceptional circumstances, review 3-monthly, and stop antibiotics as soon as possible because of antimicrobial resistance risk.",
            "Refer urgently/same day if acne fulminans is suspected; consider dermatology/GPwER referral for scarring, persistent pigmentary change, poor response to completed courses, or significant psychological distress.",
        ])

    if "menopause" in lower or "hrt" in lower:
        points.extend([
            "For people with a uterus taking systemic HRT, vaginal bleeding can be common in the first 6 months of treatment or within 3 months of changing dose or preparation.",
            "Ask about vaginal bleeding at the 3-month HRT review and advise prompt medical help for unscheduled bleeding beyond those timeframes.",
            "NICE notes limited evidence for unscheduled vaginal bleeding on sequential or continuous HRT and cites British Menopause Society guidance.",
        ])

    if "spirometry" in lower or ref == "HTG776":
        points.extend([
            "ArtiQ.Spiro can be used during the evidence generation period only after clinical assessment and with clinical oversight; it must not replace the clinician making the final asthma/COPD diagnosis.",
            "Use requires evidence generation and appropriate regulatory approval, including NHS England DTAC approval.",
            "EasyOne Connect, GoSpiro and LungHealth need more research before NHS funding for algorithm-supported asthma/COPD diagnosis.",
            "NICE flags diagnostic accuracy uncertainty, possible false-positive/false-negative results, prescribing consequences, staff resource implications and information governance risks.",
        ])

    if "non-specific low back pain" in lower or ref == "HTG712":
        points.extend([
            "April 2026 update removed Kaia from the recommendations because it is no longer available to the NHS; recommendations otherwise remain unchanged after migration to HealthTech guidance HTG712.",
            "NICE says getUBetter, Hinge Health, Pathway through Pain and SelfBack can be used in the NHS for managing non-specific low back pain in people aged 16 years and over, once appropriately approved and DTAC-compliant.",
            "Ascenti Reach, Digital Therapist, Flok Health, Phio Engage and Joint Academy are available only for people taking part in a research study.",
            "Primary care relevance is signposting/referral pathway awareness and ensuring any local digital option has DTAC approval and evidence-generation arrangements.",
        ])

    if "hyperkalaemia" in lower or ref == "TA1148":
        points.extend([
            "Sodium zirconium cyclosilicate is an option for acute life-threatening hyperkalaemia in emergency care alongside standard care.",
            "For persistent hyperkalaemia, NICE eligibility includes CKD stage 3b to 5 or heart failure, confirmed serum potassium at least 5.5 mmol/litre, inability to optimise RAAS inhibitor dose because of hyperkalaemia, and not being on dialysis.",
            "The primary care interface is formulary/shared-care clarity, potassium monitoring, RAAS inhibitor optimisation and specialist advice rather than routine unsupervised initiation.",
        ])

    if not points:
        points.append("No deterministic clinical-point extraction was available for this item; use the NICE source links and language-model analysis for clinician review.")

    return list(dict.fromkeys(points))


def _clinical_brief_from_source(item: dict, text: str) -> dict:
    title = item.get("title", "")
    ref = item.get("reference", "")
    lower = f"{title} {ref} {text}".lower()

    brief = {
        "what_changed": "No clear clinical change was identified by fallback analysis; review the NICE source before changing local practice.",
        "key_takeaways": _clinical_points_from_source(item, text)[:5],
        "practice_implication": "Awareness only unless clinician review identifies a local SOP, prescribing or pathway change.",
        "meeting_discussion": "Confirm whether this item changes local practice or should be logged for awareness only.",
        "suggested_action": "Clinical governance lead to review source and decide whether to share or file for awareness.",
        "source_basis": "Fallback analysis of NICE pages and linked source material. Use LLM mode for final clinical wording.",
    }

    if "acne" in lower or ref == "NG198":
        admin = "stakeholder list updated" in lower and "april 2026" in lower
        brief.update({
            "what_changed": "April 2026 appears to be an administrative NICE update rather than a new clinical recommendation; however acne remains highly relevant to routine primary care prescribing.",
            "key_takeaways": [
                "Offer a 12-week first-line treatment course based on severity and patient preference.",
                "For any acne severity, a fixed topical adapalene + benzoyl peroxide combination is a NICE first-line option; this corresponds to products such as Epiduo where locally formulary-approved.",
                "Other first-line options include fixed topical tretinoin + clindamycin for any severity, and fixed topical benzoyl peroxide + clindamycin for mild to moderate acne.",
                "For moderate to severe acne, combine topical therapy with oral lymecycline or doxycycline when appropriate.",
                "Review at 12 weeks; avoid prolonged antibiotic-containing regimens, continuing beyond 6 months only exceptionally with 3-monthly review.",
            ],
            "practice_implication": "Check acne template/formulary advice: first-line fixed combination topical therapy should be prominent, antibiotic duration should be actively reviewed, and referral triggers should be clear.",
            "meeting_discussion": "Do our acne prescribing templates and patient advice reflect NICE first-line fixed-combination options, 12-week review, and antibiotic stewardship?",
            "suggested_action": "Pharmacist/GP prescribing lead to check acne formulary wording and review template.",
            "source_basis": "NICE NG198 recommendations on first-line treatment options and review of first-line treatment.",
        })
        if admin:
            brief["what_changed"] = "The April 2026 NICE update appears administrative, but the standing NG198 clinical recommendations remain useful for primary care practice review."

    elif ref == "NG12":
        brief.update({
            "what_changed": "NICE updated suspected cancer recommendations, including ovarian cancer age-specific CA125 thresholds and ultrasound triggers.",
            "key_takeaways": [
                "For persistent ovarian-cancer symptoms in people aged 40 or over, measure CA125 in primary care.",
                "Arrange urgent direct-access ultrasound using age-specific CA125 thresholds: 40-49 35 IU/ml; 50-59 31 IU/ml; 60-69 24 IU/ml; 70-79 25 IU/ml; 80+ 31 IU/ml.",
                "For people aged 39 or under with persistent symptoms, do not use CA125 in isolation; consider urgent ultrasound.",
                "If ultrasound suggests ovarian cancer, refer on a suspected cancer pathway.",
                "Persistent symptoms include bloating/distension, early satiety/loss of appetite, pelvic or abdominal pain, and urinary urgency/frequency; also consider weight loss, fatigue, bowel habit change and new IBS-type symptoms in people aged 50 or over.",
            ],
            "practice_implication": "Update suspected cancer templates, ovarian cancer safety-netting and direct-access ultrasound pathway prompts.",
            "meeting_discussion": "Agree how the age-specific CA125 thresholds will be built into templates and safety-netting.",
            "suggested_action": "Cancer lead/governance lead to update suspected cancer SOP and brief clinicians.",
            "source_basis": "NICE NG12 April 2026 update and ovarian cancer recommendations.",
        })

    elif ref == "NG23" or "menopause" in title.lower():
        brief.update({
            "what_changed": "NICE amended HRT bleeding advice to align with suspected cancer guidance.",
            "key_takeaways": [
                "For people with a uterus, vaginal bleeding can be common in the first 6 months of systemic HRT or within 3 months of changing dose/preparation.",
                "Ask about bleeding at the 3-month HRT review.",
                "Advise prompt medical help for unscheduled bleeding beyond those expected windows.",
                "NICE notes limited evidence for unscheduled bleeding on sequential or continuous HRT and cites British Menopause Society guidance.",
            ],
            "practice_implication": "Update HRT counselling, review templates and patient information to include bleeding timeframes and escalation advice.",
            "meeting_discussion": "Do menopause/HRT templates ask about bleeding at 3 months and give clear escalation advice?",
            "suggested_action": "Menopause lead/prescribing lead to update HRT review template and patient information.",
            "source_basis": "NICE NG23 April 2026 update information and recommendations.",
        })

    elif ref == "QS18" or ref == "CG122" or "ovarian cancer" in title.lower():
        brief.update({
            "what_changed": "NICE ovarian cancer quality material now aligns with updated suspected cancer recommendations on age-specific CA125 thresholds.",
            "key_takeaways": [
                "Adults aged 40 or over with persistent symptoms should have urgent direct-access ultrasound if indicated by age and CA125 level.",
                "Urgent direct-access ultrasound means within 2 weeks, with primary care retaining responsibility for acting on results.",
                "Symptom triggers include bloating/distension, early satiety/loss of appetite, pelvic or abdominal pain, urinary urgency/frequency, weight loss, fatigue, bowel habit change and IBS-type symptoms in people aged 50 or over.",
            ],
            "practice_implication": "Use this as an audit/quality-standard hook for suspected ovarian cancer recognition and ultrasound access.",
            "meeting_discussion": "Should we audit recent suspected ovarian cancer presentations against CA125 and ultrasound criteria?",
            "suggested_action": "Governance lead to consider an ovarian cancer pathway audit.",
            "source_basis": "NICE QS18/CG122 content aligned with NG12.",
        })

    elif "spirometry" in lower or ref == "HTG776":
        brief.update({
            "what_changed": "NICE supports early use of ArtiQ.Spiro during evidence generation for algorithm-supported spirometry in primary care/community diagnostic settings.",
            "key_takeaways": [
                "ArtiQ.Spiro may be used only with clinical assessment and clinical oversight; it must not make the final asthma/COPD diagnosis.",
                "Use depends on evidence generation and appropriate regulatory approval, including DTAC approval.",
                "Other named tools need more research before NHS funding for this purpose.",
            ],
            "practice_implication": "Do not procure or use algorithm-supported spirometry without clinical governance, training, IG/DTAC checks and audit arrangements.",
            "meeting_discussion": "Is the practice considering algorithm-supported spirometry, and what governance safeguards are needed?",
            "suggested_action": "Respiratory lead/practice manager to review before any procurement or pathway change.",
            "source_basis": "NICE HTG776 recommendations.",
        })

    elif "hyperkalaemia" in lower or ref == "TA1148":
        brief.update({
            "what_changed": "NICE updated and replaced prior sodium zirconium cyclosilicate guidance.",
            "key_takeaways": [
                "Use is an option for acute life-threatening hyperkalaemia in emergency care alongside standard care.",
                "For persistent hyperkalaemia, eligibility includes CKD stage 3b-5 or heart failure, potassium at least 5.5 mmol/litre, RAAS inhibitor optimisation limited by hyperkalaemia, and not being on dialysis.",
                "Primary care relevance is mainly formulary/shared-care clarity, potassium monitoring and RAAS inhibitor optimisation.",
            ],
            "practice_implication": "Check local formulary/shared-care pathway before any primary care prescribing or monitoring commitments.",
            "meeting_discussion": "Does our prescribing guidance reflect TA1148 and local ICB formulary position?",
            "suggested_action": "Prescribing lead/pharmacist to confirm local position.",
            "source_basis": "NICE TA1148 recommendations.",
        })

    elif ref == "HTG712" or "non-specific low back pain" in lower:
        brief.update({
            "what_changed": "NICE removed Kaia from the low back pain digital technology recommendations because it is no longer available to the NHS; other recommendations are unchanged after migration to HTG712.",
            "key_takeaways": [
                "For people aged 16 and over with non-specific low back pain, NICE says getUBetter, Hinge Health, Pathway through Pain and SelfBack can be used in the NHS once appropriately approved and DTAC-compliant.",
                "Ascenti Reach, Digital Therapist, Flok Health, Phio Engage and Joint Academy are only available in a research-study context.",
                "Primary care should avoid signposting to Kaia as an NHS option and should check any local digital pathway against the current NICE list and DTAC/local governance requirements.",
            ],
            "practice_implication": "Update any low back pain digital self-management signposting or care-navigation material if Kaia is listed.",
            "meeting_discussion": "Do our MSK/low back pain resources list current NICE-supported digital options and remove Kaia?",
            "suggested_action": "Care navigation/MSK lead to check patient resources and local digital pathway wording.",
            "source_basis": "NICE HTG712 overview/update information and recommendations.",
        })

    return brief


def _clinical_points_by_heading_from_source(item: dict) -> list[dict]:
    groups: list[dict] = []
    for page in item.get("source_pages", []) or []:
        heading = page.get("title") or page.get("url") or "NICE source"
        text = page.get("text", "")
        points = _extract_generic_clinical_points(text)
        if not points:
            points.extend(_clinical_points_from_source(item, text))
        points = list(dict.fromkeys(points))[:12]
        if points:
            groups.append({
                "heading": heading,
                "source_url": page.get("url", ""),
                "points": points,
            })
    return groups


def _extract_generic_clinical_points(text: str) -> list[str]:
    """Conservative deterministic extraction for no-LLM/sample runs.

    The production path asks the LLM to analyse each heading. This fallback keeps
    clinically specific sentences visible when running without an API key.
    """
    points: list[str] = []
    normalised = re.sub(r"\s+", " ", text).strip()
    if not normalised:
        return points

    sentence_candidates = re.split(r"(?<=[.!?])\s+|(?<=\])\s+", normalised)
    keywords = (
        "recommend", "refer", "referral", "offer", "consider", "measure", "arrange",
        "urgent", "within", "threshold", "symptom", "diagnos", "monitor", "review",
        "prescrib", "dose", "dosage", "contraindicat", "safety", "risk", "evidence",
        "primary care", "clinical oversight", "must", "can be used", "not be used",
        "not recommended", "eligible", "criteria", "serum", "ultrasound", "ca125",
        "hormone replacement therapy", "hrt", "hyperkalaemia", "spirometry",
        "asthma", "copd", "kidney", "heart failure", "dialysis", "2 weeks",
        "90 days", "dtac",
    )
    for sentence in sentence_candidates:
        clean = sentence.strip(" -•\t\n")
        if len(clean) < 45 or len(clean) > 500:
            continue
        lower = clean.lower()
        if any(keyword in lower for keyword in keywords):
            points.append(clean)
        if len(points) >= 10:
            break

    table_lines = []
    in_tables = False
    for line in text.splitlines():
        if "Extracted tables:" in line:
            in_tables = True
            continue
        if in_tables and line.strip():
            table_lines.append(line.strip())
    if table_lines:
        points.append("Source table content: " + "; ".join(table_lines[:8]))

    return points
