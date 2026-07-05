import { SessionStream } from "@/components/session-stream";

// Next 16: params artik Promise. Server component await eder, id'yi client'a gecirir.
export default async function SessionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <SessionStream id={id} />;
}
