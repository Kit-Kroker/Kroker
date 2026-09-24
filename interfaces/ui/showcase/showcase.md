# Showcase

The showcase renders every registered profile set (`showcase/registry.ts`)
as one article per profile: a heading, the summary line, and a stage
hosting the live component with the profile's props bound
(`interfaces/ui/showcase/Showcase.vue`). It is the rendering surface for
the design-system pane and the presentation tier: each article is
addressed as `#showcase-<component>-<profile>` (`src/profile.ts`).

## Requirements

### SHOWCASE-1
A profile's text slots render inside its stage: each `Profile.slots`
entry is passed to the component as named-slot content (the default slot
when the key is `default`), as plain text interpolation -- never `v-html`.
[FR-014]

## Failure modes

A slot-using profile rendered without its slot text shows an empty
control and fails presentation testing (SHOWCASE-1). Slot text injected
as HTML rather than interpolated is out of contract and never asserted
on: SHOWCASE-1 checks text, so markup injection cannot pass it.
