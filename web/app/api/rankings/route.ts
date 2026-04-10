import { NextResponse } from 'next/server';
import { buildPlayerIndex, readRankingFile } from '@/lib/data';

export function GET() {
  return NextResponse.json({
    meta: readRankingFile(),
    players: buildPlayerIndex(),
  });
}
