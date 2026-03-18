# Product QA Checklist

Use this checklist when reviewing mocked or future live `/score` responses for the Chicago MVP.

## Trust and interpretation checks
- Does the score band match the explanation tone?
- Does the explanation sound appropriately cautious for low-confidence cases?
- Does the output avoid sounding more certain than the underlying evidence supports?
- Would a normal homebuyer understand the headline takeaway without seeing internal model details?

## Confidence checks
- Does the confidence label match the quality of the source evidence?
- Does the confidence label reflect timing specificity, not just severity?
- Does precise address-level and date-level evidence score more confidently than broad permit evidence?

## Top-risk checks
- Are the top risks understandable to a normal homebuyer?
- Are the top risks phrased as practical impacts rather than internal system terms?
- Do the top risks reinforce the same dominant driver described in the explanation?

## Category and severity checks
- Are risk categories internally consistent across score, severity, top risks, and explanation?
- Does `traffic` behave like access friction rather than general neighborhood inconvenience?
- Do `noise` and `dust` only rise when the supporting work type reasonably suggests those impacts?
- Are HIGH severity labels reserved for clearly decision-relevant disruption?

## QA address review checks
- For each of the 18 QA addresses, is the expected disruption tier still plausible?
- Do high-band examples feel materially more disruptive than moderate-band examples?
- Do low-band examples avoid alarming language unless evidence clearly warrants it?

## Output discipline checks
- Does the response stay inside the documented API contract?
- Is the explanation short, concrete, and deterministic?
- Would the response still feel credible if shown in a buyer-facing demo?
