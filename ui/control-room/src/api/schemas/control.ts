import { z } from "zod";
import { controlSchema } from "./workflow";

// POST /api/v1/control/actions — the T5.3a seam (bin/control_room_control.py FORWARDED_KEYS).
export const controlActionIdSchema = z.enum(["pause", "resume", "run_now", "retry", "stop"]);
export type ControlActionId = z.infer<typeof controlActionIdSchema>;

export const controlRequestSchema = z.object({
  workflow_id: z.string(),
  action: controlActionIdSchema,
  reason: z.string().optional(),
  stage: z.enum(["preview", "apply"]).optional(),
  preview_token: z.string().optional(),
  trigger: z.string().optional(),
  confirm: z.literal(true).optional(),
  retry_of: z.string().nullable().optional(),
});
export type ControlRequest = z.infer<typeof controlRequestSchema>;

export const refusalSchema = z
  .object({
    code: z.string(),
    message: z.string().nullish(),
    choices: z.array(z.string()).nullish(),
  })
  .catchall(z.unknown());

export const unitStateSchema = z
  .object({ state: z.string().nullish() })
  .catchall(z.unknown());

export const controlReceiptSchema = z
  .object({
    receipt_id: z.string().nullish(),
    workflow_id: z.string().nullish(),
    action: z.string().nullish(),
    stage: z.string().nullish(),
    trigger: z.string().nullish(),
    reason: z.string().nullish(),
    requested_at: z.string().nullish(),
    completed_at: z.string().nullish(),
    before: unitStateSchema.nullish(),
    after: unitStateSchema.nullish(),
    result: z.string().nullish(),
    refusal: refusalSchema.nullish(),
    commands: z.array(z.unknown()).nullish(),
    run_id: z.string().nullish(),
    next_scheduled_run: z.string().nullish(),
    catch_up_fired: z.boolean().nullish(),
    implication: z.unknown().nullish(),
    note: z.string().nullish(),
    links: z.record(z.string(), z.unknown()).nullish(),
  })
  .catchall(z.unknown());

export const controlPreviewSchema = z
  .object({
    preview_token: z.string().nullish(),
    implication: z
      .object({ message: z.string().nullish(), catch_up_fired: z.boolean().nullish() })
      .catchall(z.unknown())
      .nullish(),
  })
  .catchall(z.unknown());

export const controlResponseSchema = z.object({
  receipt: controlReceiptSchema.nullish(),
  control: controlSchema.nullish(),
  preview: controlPreviewSchema.nullish(),
  error: z.string().nullish(),
});

export type ControlResponse = z.infer<typeof controlResponseSchema>;
export type ControlReceipt = z.infer<typeof controlReceiptSchema>;
export type Refusal = z.infer<typeof refusalSchema>;
