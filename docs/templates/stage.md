# <Stage> Stage

One paragraph: what this stage does in the pipeline, what it consumes,
what it produces. Name the artifact type and where it lives.

What the caller owns versus what this stage owns. Be specific -- the
boundary is the whole point of the document.

## Requirements

<STAGE>-1. A requirement, stated as a property of the stage's behaviour,
in one sentence. [FR-xxx]

<STAGE>-1.1. A sub-clause narrowing the parent: an edge case, a failure
mode, or a state transition the parent implies but does not pin down.
[FR-xxx]

<STAGE>-2. The next requirement. Each clause carries exactly one
obligation -- if you need "and", it is two clauses. [E-xx]

## Failure modes

What this stage does when its inputs are wrong, when a model returns
something unusable, and when a human never answers. Each one anchored to
the clause that governs it.
