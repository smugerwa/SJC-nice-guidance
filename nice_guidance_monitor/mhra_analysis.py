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
    You are creating an internal UK primary care clinical governance report from MHRA alerts, recalls and safety updates.
    Use only the supplied MHRA source text. Do not invent dates, batches, products, warnings, recommendations or actions.
    Distinguish mandatory action from awareness-only local good practice. Do not give individual patient advice.

    Return strict JSON with these keys:
    included boolean;
    exclusion_reason string;
    guidance_identification object with title, source_reference, guidance_type, publication_or_update_date, url, status;
    clinical_brief object with what_changed string, key_takeaways array of 3 to 6 concise clinician-facing bullet strings, practice_implication string, meeting_discussion string, suggested_action string, source_basis string;
    plain_english_summary array of 3 to 6 strings;
    key_clinical_points array of concise clinically specific strings, including affected medicines/devices, batch or product scope, patient risk, stock action, prescribing/dispensing implications, patient contact criteria, monitoring, deadlines and escalation routes where present;
    relevance object with score integer 0-5, rationale string, staff_groups array;
    required_actions array of objects with classification, owner, deadline, priority, reason, meeting_note_wording;
    impact_assessment object with clinical, operational, prescribing, referral_pathway, patient_communication, governance_cqc, financial_resource;
    recommended_communication object with gp_meeting, nurse_pharmacist_update, admin_care_navigation_update;
    source_urls array;
    source_incomplete boolean.

    Include only items with a realistic UK GP primary care or dispensing-practice interface in the main brief. Put specialist-only hospital/device items with no GP action into appendix/excluded status.

    Item metadata:
    {json.dumps(item, ensure_ascii=False)[:5000]}

    MHRA source material:
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
    result["raw_item"] = item
    return _normalise_result(result, item)


def fallback_analysis(item: dict, config: dict) -> dict:
    title = item.get("title", "")
    ref = item.get("reference", "")
    alert_type = item.get("alert_type", "")
    issued = item.get("issued", "")
    text = "\n".join(page.get("text", "") for page in item.get("source_pages", []))
    combined = f"{title} {alert_type} {' '.join(item.get('medical_specialisms') or [])} {item.get('summary', '')} {text}"
    lower = combined.lower()

    score = 1
    included = False
    reason = "No clear routine primary care action identified by fallback analysis."
    staff = ["Clinical governance lead"]
    priority = "low"
    action_class = "Awareness only"

    high_signal_terms = (
        "general practice", "dispensing gp", "primary care", "community pharmacy",
        "patient level", "patients should", "contact patients", "recall all batches",
        "class 1", "national patient safety alert", "quarantine", "stop using",
        "do not use", "risk of overdose", "risk of harm",
    )
    prescribing_terms = (
        "medicine", "medicines", "tablet", "capsule", "oral solution", "inhaler",
        "injection", "cream", "ointment", "eye drops", "pil", "patient information leaflet",
        "batch", "batches", "recall", "defect notification", "pharmacy", "wholesaler",
        "dispensing",
    )
    common_primary_care_terms = (
        "ramipril", "apixaban", "baclofen", "ibuprofen", "amitriptyline",
        "prednisolone", "melatonin", "clarithromycin", "hrt", "vaccine",
        "antibiotic", "anticoagulant", "cardiovascular", "respiratory",
        "dermatology", "psychiatry", "paediatric", "paediatrics",
    )
    negative_primary_care_terms = (
        "no gp prescribing",
        "no gp action",
        "no primary care action",
        "no routine primary care",
        "no gp prescribing, dispensing, patient contact or primary care pathway action",
        "no prescribing, dispensing, patient contact or primary care pathway action",
    )

    if any(term in lower for term in high_signal_terms):
        included = True
        score = 4
        reason = "The alert has a likely GP, prescribing, patient-contact or dispensing-practice interface."
        staff = ["GP", "pharmacist", "dispensary lead", "practice manager", "care navigation"]
        priority = "medium"

    if any(term in lower for term in negative_primary_care_terms):
        included = False
        score = 1
        reason = "The MHRA item appears to have no stated GP prescribing, dispensing, patient-contact or pathway action."
        staff = ["Clinical governance lead"]
        priority = "low"
        action_class = "Check stock and pathway impact"
    if "national patient safety alert" in lower or "class 1" in lower:
        included = True
        score = 5
        reason = "National patient safety or Class 1 recall with potential urgent practice action."
        priority = "urgent"
        action_class = "Immediate safety action"
    elif any(term in lower for term in prescribing_terms) and any(term in lower for term in common_primary_care_terms):
        included = True
        score = max(score, 3)
        reason = "Medicine alert involving a product or therapeutic area commonly encountered in primary care."
        staff = ["GP", "pharmacist", "dispensary lead"]
        priority = "medium"

    takeaways = _extract_action_sentences(combined)
    if not takeaways:
        takeaways = [
            "Review the MHRA source page for affected product, batch and action details before changing practice.",
            "Check whether the product is prescribed, administered, stored or dispensed by the practice.",
            "Escalate to the prescribing lead or dispensary lead if affected stock or patients may be present.",
        ]

    actions = []
    if included:
        actions.append({
            "classification": action_class,
            "owner": "Prescribing lead/pharmacist or dispensary lead",
            "deadline": "Within 2 working days, or sooner if the MHRA alert states an urgent deadline",
            "priority": priority,
            "reason": reason,
            "meeting_note_wording": f"{ref or 'MHRA'}: confirm whether affected stock, prescribing templates, patient contact or staff briefing is needed.",
        })
    practice_implication = "File for awareness unless local use of the product/device is identified."
    meeting_discussion = "Is there any local use or patient-facing implication that means this should be escalated beyond awareness?"
    suggested_action = "Clinical governance lead to file for awareness; no GP action identified by fallback analysis."
    if included:
        practice_implication = "Check whether the practice prescribes, stores, administers or dispenses the affected product; document the decision and any patient/stock actions."
        meeting_discussion = "Does this MHRA item require stock checks, patient contact, prescribing-template changes or staff briefing in our GP setting?"
        suggested_action = actions[0]["meeting_note_wording"]

    result = {
        "included": included,
        "exclusion_reason": "" if included else reason,
        "guidance_identification": {
            "title": title,
            "source_reference": ref,
            "guidance_type": alert_type,
            "publication_or_update_date": issued,
            "url": item.get("url", ""),
            "status": "issued",
        },
        "plain_english_summary": takeaways[:5],
        "clinical_brief": {
            "what_changed": item.get("summary") or "MHRA issued a safety alert/update. Review the source for affected product and action details.",
            "key_takeaways": takeaways[:6],
            "practice_implication": practice_implication,
            "meeting_discussion": meeting_discussion,
            "suggested_action": suggested_action,
            "source_basis": "Fallback analysis of MHRA GOV.UK alert page; clinician sign-off required.",
        },
        "key_clinical_points": takeaways,
        "relevance": {"score": score, "rationale": reason, "staff_groups": staff},
        "required_actions": actions,
        "impact_assessment": {
            "clinical": reason,
            "operational": "Check local stock, dispensing and patient-contact workflow if relevant.",
            "prescribing": "Confirm whether local prescribing templates, formularies or repeat prescriptions mention the product.",
            "referral_pathway": "No referral pathway change identified unless specified in the MHRA alert.",
            "patient_communication": "Contact affected patients only where the MHRA alert or local stock review indicates this is needed.",
            "governance_cqc": "Keep the MHRA source log and document the practice decision/action.",
            "financial_resource": "Likely low unless stock replacement or patient recall is needed.",
        },
        "recommended_communication": {
            "gp_meeting": actions[0]["meeting_note_wording"] if actions else "",
            "nurse_pharmacist_update": "Share with prescribing/dispensing staff if the product is used locally.",
            "admin_care_navigation_update": "Brief reception/care navigation only if patients may ask about affected products.",
        },
        "source_urls": [page.get("url") for page in item.get("source_pages", [])] or [item.get("url", "")],
        "source_incomplete": item.get("source_incomplete", False),
        "raw_item": item,
    }
    return _normalise_result(result, item)


def _normalise_result(result: dict, item: dict) -> dict:
    ident = result.setdefault("guidance_identification", {})
    ident.setdefault("title", item.get("title", ""))
    ident.setdefault("source_reference", item.get("reference", ""))
    ident.setdefault("guidance_type", item.get("alert_type", ""))
    ident.setdefault("publication_or_update_date", item.get("issued", ""))
    ident.setdefault("url", item.get("url", ""))
    ident.setdefault("status", "issued")
    # Existing report builders understand nice_reference; keep it as a compatibility alias.
    ident.setdefault("nice_reference", ident.get("source_reference", "MHRA"))
    result.setdefault("source_urls", [item.get("url", "")])
    result.setdefault("source_incomplete", item.get("source_incomplete", False))
    result.setdefault("raw_item", item)
    return result


def _extract_action_sentences(text: str) -> list[str]:
    normalised = re.sub(r"\s+", " ", text).strip()
    if not normalised:
        return []
    keywords = (
        "recall", "quarantine", "return", "stop", "do not use", "contact",
        "patient", "batch", "batches", "risk", "monitor", "check", "pharmacy",
        "dispensing", "prescrib", "safety", "overdose", "defect", "information leaflet",
    )
    points = []
    for sentence in re.split(r"(?<=[.!?])\s+", normalised):
        clean = sentence.strip(" -\t\n")
        if len(clean) < 35 or len(clean) > 450:
            continue
        lower = clean.lower()
        if "alert type:" in lower or "medical specialism:" in lower:
            continue
        if any(keyword in lower for keyword in keywords):
            points.append(clean)
        if len(points) >= 8:
            break
    return list(dict.fromkeys(points))
