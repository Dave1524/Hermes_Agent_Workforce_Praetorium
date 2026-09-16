import { z } from "zod";

// Keys vary per endpoint (manifests, contracts, receipts, systemd, benefitLedger, incidentState);
// each is one of available | degraded | unavailable, and `errors` maps the same keys to lists.
export const dataStatusSchema = z
  .object({ errors: z.record(z.string(), z.unknown()).optional() })
  .catchall(z.unknown());

export type DataStatus = z.infer<typeof dataStatusSchema>;
