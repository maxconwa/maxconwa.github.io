---
title: Linear algebra for robotics
summary: Vectors, matrices and transforms — the minimum needed before anything else here makes sense.
prereqs: []
track: Math foundations
updated: 2026-09-17
---

*Placeholder. The lesson text goes here.*

## What this covers

A rotation in three dimensions is a matrix $R \in SO(3)$ satisfying
$R^\top R = I$ and $\det R = 1$. Composing two of them is a matrix product,
which is why transforms chain so cleanly along a kinematic tree.

## Why it comes first

Every other lesson in this section leans on it: gradients are linear maps,
rigid-body transforms are matrices, and covariance is a quadratic form.
