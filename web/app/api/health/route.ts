// A pure liveness probe. Health checks must answer within a few seconds, so this opens no
// database connection and imports nothing heavy; readiness is a separate concern.
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ ok: true });
}
