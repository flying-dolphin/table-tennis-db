"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";

export default function DataExplanationPage() {
  const router = useRouter();

  return (
    <div className="max-w-3xl mx-auto px-5 py-8">
      <button
        onClick={() => router.back()}
        className="flex items-center text-sm text-gray-500 hover:text-gray-900 transition-colors mb-6"
      >
        <ArrowLeft className="w-4 h-4 mr-1.5" />
        返回
      </button>

      <h1 className="text-2xl font-bold mb-6">数据统计说明</h1>
      <div className="prose prose-sm sm:prose-base text-gray-700 space-y-4">
        <p>本平台当前阶段暂时只提供最近10年的女乒数据。</p>
        <p>赛事仅包括成年组赛事，仅包括WTT和ITTF进入积分规则的赛事，以及之前较重要的巡回赛和公开赛。不包括T2之类的赛事。</p>
        <p>后续会逐步增加男乒数据、更多赛事和更多统计口径的数据。</p>

        <h2 className="text-lg font-semibold mt-6 mb-2">数据来源</h2>
        <p>所有数据均来源于：</p>
        <ul className="list-disc pl-5 space-y-1">
          <li>国际乒联 (ITTF) 官方网站及公开接口</li>
          <li>世界乒乓球职业大联盟 (WTT) 官方公布的赛事资料</li>
          <li>公开的赛事转播与新闻报道</li>
        </ul>

        <h2 className="text-lg font-semibold mt-6 mb-2">统计口径</h2>
        <p>以下数据均以官方统计数据为准：</p>
        <ul className="list-disc pl-5 space-y-1">
          <li><strong>排名数据：</strong>以国际乒联官方每周公布的最新世界排名为准。</li>
          <li><strong>赛事积分：</strong>严格按照《ITTF乒乓球世界排名规则》进行计算与核对。</li>
          <li><strong>比赛成绩：</strong>以赛事组委会最终公布的官方成绩单为准。</li>
        </ul>
        <p>其他统计指标均基于上述赛事范围的数据自行计算，因为本人水平和精力有限，可能存在错误，欢迎指正。</p>

      </div>
    </div>
  );
}
