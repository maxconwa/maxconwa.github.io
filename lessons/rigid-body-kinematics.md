---
title: Rigid body kinematics
summary: Forward kinematics on a humanoid, and why the Jacobian is the object you actually care about.
prereqs: [linear-algebra]
track: Humanoid autonomy
updated: 2026-09-17
---

*Placeholder. The lesson text goes here.*

## What this covers

Forward kinematics composes transforms down a chain. The Jacobian $J(q)$
relates joint velocity to end-effector velocity, $\dot{x} = J(q)\,\dot{q}$,
and its structure tells you where the arm loses a degree of freedom.
