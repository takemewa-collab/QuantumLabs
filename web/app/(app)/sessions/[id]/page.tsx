import { ChatSession } from "@/components/chat-session";

// Next 16: params artik Promise. Server component await eder, id'yi client'a gecirir.
export default async function SessionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  // key={id}: baska session'a gecince ChatSession REMOUNT olur -> tum state
  // (events/pending/linesSeen) dogal sifirlanir (effect icinde toplu setState yok).
  return <ChatSession key={id} id={id} />;
}
