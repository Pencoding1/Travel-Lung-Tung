# Human study protocol — H1

Prepared2026-10-15; NOT EXECUTED. Target10–15 real consenting adults, convenience sample suitable for an exploratory graduation project. Recruitment and institutional/supervisor requirements must be handled by the study owner. No participant contact has been made and no responses exist.

## Design

Within-participant comparison of tool-chain visible vs hidden. Use four frozen travel-answer stimuli, including a grounded success, insufficient data and a tool failure, with source-grounded correctness labels. Each participant sees both conditions across matched stimuli, never two separately generated versions of the same content. Alternate AB/BA order using a fixed balanced assignment list; rotate stimulus-condition mapping. Keep answer text, layout, latency demonstration, source facts and response length unchanged except the trace component. Trace shows tool name, safe argument summary, outcome and data source; do not expose private reasoning, secrets or raw private records.

Use a neutral practice task. Explain that this is a research prototype and some outputs may be limited. Participants can withdraw without penalty or skip a question. Record age eligibility, prior AI familiarity and condition order, but no names/contact details in the response dataset. Store consent separately using anonymous participant IDs. Owner specifies retention period and withdrawal deadline before recruitment; until then this protocol is not ready to administer.

## Questionnaire (study-specific, not a validated scale)

For each condition rate1=strongly disagree through5=strongly agree; allow unanswered. Vietnamese wording below is authored for this task, not a validated translation of TIAS or another published instrument.

1. Tôi tin rằng các thông tin về địa điểm trong câu trả lời này có căn cứ.
2. Tôi hiểu hệ thống đã dựa vào thông tin nào để đưa ra câu trả lời.
3. Tôi có thể nhận ra những phần thông tin mà hệ thống chưa kiểm chứng.
4. Tôi hài lòng với cách hệ thống trình bày câu trả lời.
5. Tôi sẵn sàng dùng câu trả lời này để lập kế hoạch, sau khi kiểm tra những thông tin còn thiếu.

Primary H1 outcome: item1 per participant, averaged over assigned stimuli in each condition. Items2–5 are secondary distinct constructs; do not average all into a validated trust score. Ask a separate factual reliance decision: which information would you verify before travelling, and which unsupported statement (if any) would you reject? These decisions help identify overtrust but do not establish population calibration.

Open response: Điều gì khiến bạn tin hoặc không tin câu trả lời? Optional; strip accidental identifying information before sharing excerpts.

## Analysis fixed before collection

Report actual N, exclusions with reasons, missingness, order allocation and stimulus exposure. Primary paired difference=visible−hidden for each participant. Report paired means, medians, every anonymized participant difference and bootstrap95% interval (participant resampling, fixed seed20261015,10000 draws). Given small ordinal/convenience sample, use an exact sign test on nonzero participant differences as a robust exploratory test; ties reported and excluded only from that test denominator. Two-sided alpha.05; positive direction is required to support H1. A null or negative result is retained. Secondary outcomes descriptive; label multiplicity and avoid selective claims.

Do not infer that higher subjective trust proves correctness. System evidence and human evidence answer different questions. This design cannot establish general population effects, long-term adoption or causal effects of the entire agent architecture. Report stimulus/order effects and familiarity limitations.

## Data dictionary and empty schema

participant_id, consent_version, order_group, stimulus_id, condition, item1, item2, item3, item4, item5, verification_choice, open_comment, completion_timestamp, excluded_reason.

No fabricated example responses are included. A separate synthetic file may test analysis code only if explicitly labelled and excluded from study results. Publish aggregates only after owner-approved handling; never upload consent forms or identifying data to model providers.

## Research context

Metzger et al., CHI2024, found communication style affected trust in their mock-agent study while prior disclaimers did not; this motivates controlling wording and measuring reliance separately. It does not validate our questionnaire or predict H1. [Primary paper](https://doi.org/10.1145/3613904.3642122).

Before administration: freeze stimuli and assignment; owner confirms consent/retention/supervisor process; pilot comprehension without adding pilot data to final analysis; recruit real participants. These actions are pending, not approval requests for unrelated implementation.
