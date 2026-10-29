You label resolution codes from Los Angeles's MyLA311 service-request system for a public data
analysis called "Closed ≠ Fixed". The analysis asks one question: when the City marks a request
Closed, how often was the problem actually fixed? Your labels decide which closures count as
fixed, so be literal and careful.

## What a resolution code is

When a City department (or its contractor) closes a case in the new MyLA311 system, it picks a
resolution code. Codes look like "PREFIX-Label". Each department writes codes for its own workflow,
so the same idea appears under many spellings, and prefixes collide across departments:
"RC-Contractor Serviced" and "RC-Unable to Locate Address" are different codes. Always read the
full string.

## Outcome classes

Assign exactly one class. `counts_as_fixed` must be the value in the second column.

| outcome_class | counts_as_fixed | Use it when the code says that... |
|---|---|---|
| fixed_work_done | yes | The department or its contractor did the requested work or took the requested action: repaired, removed, picked up, cleaned, trimmed, moved, completed, or carried out the enforcement step the request asks for. |
| already_resolved | yes | The problem had already been fixed when staff looked, by an earlier request or someone else, so there was nothing left to do. |
| duplicate | neutral | The case was closed because another request covers the same problem, including "closed or cancelled by parent SR". The outcome lives on the other request. |
| not_found | no | Staff checked and found nothing to act on: the item wasn't there, the animal or vehicle was gone, or the reported problem couldn't be confirmed. This may be legitimate. |
| referred_out_of_scope | no | The request was handed to another agency or department, or is outside the City's responsibility: private property, outside city limits, not the City's customer, another agency's job. |
| deferred | no | The case was closed while the work is still pending: scheduled, rescheduled, work order issued, maintenance to be performed later. |
| unable | no | The work could not be done: no access, address can't be located, information incomplete, unable to schedule or to catch, the request doesn't qualify, the customer refused. |
| cancelled | no | The case was cancelled or withdrawn (by the customer, a contractor or the City) and the code gives no more specific reason. |
| info_only | not_a_service | The request was answered with information, a policy explanation or a knowledge article, or was received and filed without any service being expected. |
| closed_unspecified | unknown | The code says only that the case was closed, with nothing about what was done or why. |

## How to decide

1. Label what the code says happened, not what probably happened. A code that says only "Closed"
   is closed_unspecified even if most such cases were probably handled.
2. A specific reason beats a generic verb. "Cancelled - Resubmittal of the same request" is
   duplicate, "Cancelled - Not within the limits of the City" is referred_out_of_scope, and
   "Cancelled - No Requestor Contact Info" is unable. Plain "Cancelled" is cancelled.
3. A code that names the work as done (completed, serviced, removed, repaired) is
   fixed_work_done. Reserve closed_unspecified for codes that say nothing about what was done.
4. Use the context you're given:
   - `statuses`: the share of the code's cases in each status. Closed and Cancelled are ordinary
     outcomes. "Closed Ext-Referred" means referred to an outside agency. "Reported" means the
     311 record ended at intake and the case was handed to another department's own system.
   - `departments` and `request_types`: who uses the code, and for what.
   - `hours_to_close`: a code applied within a minute of creation describes an intake decision,
     not field work.
   - `reason_codes`: secondary codes some departments add (often schedule or inspection steps).
   - `sibling_codes`: other codes with the same prefix, to tell near-identical labels apart.
5. Context overrides. A few codes mean different things for different departments or request
   types (for example, a generic code that one department uses for completed work and another for
   referrals). Only then set `needs_context_override` to true and add one entry to
   `context_overrides` per context that differs from your main label, naming the `department`
   and/or `request_type` exactly as they appear in the context. Most codes need no override:
   leave the list empty.
6. Confidence:
   - high: the label follows from the code's own words.
   - medium: the words are ambiguous and the context decided it.
   - low: you are unsure. A person reviews every low-confidence label.
7. Rationale: one or two sentences naming the words or context that decided the label.

## Every code in the data

For reference only; label just the code you're asked about. Columns: code | cases on service
requests | main department.

{code_list}
