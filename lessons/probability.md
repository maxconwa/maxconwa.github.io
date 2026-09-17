---
title: Probability for estimation
summary: Distributions, expectation and Bayes' rule, aimed at robots that must act on uncertain information.
prereqs: []
track: Math foundations
updated: 2026-09-17
---

*Placeholder. The lesson text goes here.*

## What this covers

Bayes' rule, written the way it gets used in a filter:

$$
p(x_t \mid z_{1:t}) \propto p(z_t \mid x_t)\, p(x_t \mid z_{1:t-1})
$$

The left side is the belief after a measurement; the right side is a
likelihood times a prediction.
