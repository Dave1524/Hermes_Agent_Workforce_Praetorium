import { z } from "zod";

// bin/workflow_requires.py: `satisfied` is tri-state — null when the bus answered nothing.
export const requirementSchema = z.object({
  unit: z.string(),
  scope: z.string().nullish(),
  workflow: z.string().nullish(),
  state: z.string().nullish(),
  satisfied: z.boolean().nullish(),
});

export const dependentSchema = z.object({
  workflow: z.string(),
  enabled: z.boolean().nullish(),
});

export type Requirement = z.infer<typeof requirementSchema>;
export type Dependent = z.infer<typeof dependentSchema>;
