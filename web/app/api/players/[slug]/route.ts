import { NextResponse } from 'next/server';
import { getPlayerDetail } from '@/lib/data';

export async function GET(_: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const detail = getPlayerDetail(slug);
  if (!detail) {
    return NextResponse.json({ error: 'Player not found' }, { status: 404 });
  }

  return NextResponse.json(detail);
}
