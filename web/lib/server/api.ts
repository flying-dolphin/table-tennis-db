import { NextResponse } from 'next/server';

type ApiMeta = Record<string, unknown>;

export function ok<T>(data: T, meta: ApiMeta = {}) {
  return NextResponse.json({
    code: 0,
    message: 'ok',
    data,
    meta,
  });
}

export function error(status: number, code: number, message: string, detail?: string) {
  return NextResponse.json(
    {
      code,
      message,
      error: {
        type: status >= 500 ? 'server_error' : 'request_error',
        detail: detail ?? message,
      },
    },
    { status },
  );
}
