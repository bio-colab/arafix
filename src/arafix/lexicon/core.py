"""
معجم نواة خفيف مضمَّن — لحسم انقلاب لام-ألف **المُبهَم** الشائع.

الفلسفة
--------
النواة ترفض التخمين الإملائي العام. هذا المعجم **استثناء مقصود ومحدود**:
كلمات عربية شائعة تُستعمل فقط كشاهد ثنائي عند مبادلة «ا/ل» المشتبهة
(انظر ``arafix.lamalef``): تُقبل المبادلة إذا كان الأصل غائباً عن المعجم
والمرشَّح حاضراً فيه.

- بلا تبعيّات: ``base64`` + ``zlib`` من المكتبة القياسية.
- تحميل كسول: لا يُفك الضغط إلا عند أول استدعاء لـ ``get_core_lexicon``.
- المصدر التاريخي: قائمة كلمات عربية مضغوطة (انظر CHANGELOG / add/).

الاستعمال
---------
::

    from arafix.lexicon.core import get_core_lexicon
    vocab = get_core_lexicon()
"""

from __future__ import annotations

import base64
import zlib
from functools import lru_cache

__all__ = [
    "COMPRESSED_LEXICON",
    "get_core_lexicon",
    "core_lexicon_size",
    "clear_core_lexicon_cache",
]

# base85(zlib(utf-8 words joined by newlines)) — ~7.4KB on disk, ~1.8k entries (enhanced with legal, academic, and common words).
COMPRESSED_LEXICON = """c-nPb*<s_llKoeh6T`d!+SbCWEc*3TgQgamrev9pM9yZ2LM`WjnjZ<L2x3Q}Ht>J`^S`Ude;=ox^&`!R{P*ZI@$<_P8%u0gk3WyI(LDL{ieR6?MZgOriT<-M6(Qj*!&_;|pU3^@*GyM1MU^GFE6I&#`T6BpeqMhXX{kNZzWnhnlx!P&zWHgQ9C^N-M`Z7mpMUb-&Tu0?Gx{t2mSpn8qlculGq*;n-j~An@{`ktM=SZhb5aK4@jEBq<tG<<c#PIBPv!yu<Z(NcaeJI0Sq9i)ZpvXERh<@3mRb~0rk`DTHbo02Y=HyHW(}Hbv^{AJ`t~-Ift&yG2p=T#{QAe7v9;k(kH3%3W^gXxakHrckju?I?qbaljOV$awSf&iwO*#j1#5IrN*(7~Wqcl!!S5(_hV!^RgJm!a$t%i0mQ`LziKjH#R!A|oDdsQ5w4@m8#ABUetW#`|-0A;5+OpUR=<<wuQmPkloHGpuE|iQ+GbkG_;67lVXVbudm5y_^CMs6w<@(eZkoj=12@r40qYPjVNh%9#+2~{y;O)-I$mG=RJZDaAFbmb-<^P$P#3n%N3E7{=fITFw;R@h&8Nd@jsrGje?$MhJr^1gE%Ch(kkjl<X5E?i?`!vwydS#6YJYv(2wkjkUO+VI+D+I6a$gMf%*4Q}zd7NYsw*d!8Mj<C*7QX|Iu`>STQ!SF)+@%UaK{Mfua5t9>u%T*Z812cujEc^}_V+P9=iHabevbJ#%icI51n`c{JIlmFA%ks(3_ft;&Up-?t>>Rt9FjBcoebyYAM>1Hk05F+M`XY~SF%_BBk<x0;W9(OE|Tw&gbYJI2?Fd1#18wzTqeU$Ear}_D=?l0OI)*bQW0YKFEalfL8yC%kadq$?QymC*s2WRNefBN2FteRMcW7O%U~O0*K>ml8~}1LG<z9(Yu@q6J0`uZyfQzdjf1rRjBp}=y(@$_f;g?iym_Fgyi2?4xsk91K*Yj(e6i<O`X`y^5~!|^NM7eBzXINn&knJn1|FGDsv^r?u@wi|s8L&-MGE-c1_${g7v@0rbcgUQzz!Eeh5#BoTt0Y<kMltWt8FYYT1@RI^4L4)7zxBkDCEp{+&QDjOt26~Syl{j2AzO~wlONB9B@+wIeRzP@Q!fMRzRLUlF(S<&Li&m5n0-ZEN$fTaKzEN=Mx5>2?5`|XB8vhL=A|gIcBjhz#5P74B^b1;ao|Kuq>nB1o7Q1uGVoDV>bbs#~%dLv<8`PhB2bJ0ItkNu6&AKXQn>O#Q_I?3Owcd_{Nj#D%%Vo?0_pT`MjxtdEI7~@WRi(<K5e=AOKiHGN$dut4ScTm>aY08_x0Pe9Hb4fI9ri^2wc#5P>n~cUjiI0M2j2I=G8o9k3`-0oS;bCqC2)>;n!cUQAqbfiD3+xTq^`_^C`sz)#Nn73*(e8D}c$rGX6&+=SwPfqis+hWKW~rS7SxIE~-Tn!bfoLTkTSxclZ&$|_q+fHDh@!@`K^<;jwh1qcH)G{d>6A?^eLU-|SgnZX1@G(+xP5a4~E)H(SI<IOtgAK6ZWcUI2Byd&UwUdZ==J-<Bw6A%bRjhyx7GnqAVNRn8ogtvgWTxQrrF|S3^FV>I+Day#icR0#sLK{WCf&w)Inyc5j6DL?$Kd;g9bvf@U7){B`rilSq%L&m2{Knx~`=-oEZ2Vg0DBi<&HgLih2<<5l+G7MP8-<txv4lM^3t1Px;$3e>Zp25JAB?b{_XSiXXBXw65^xSTV1jW1y}89_kUYlh2*783BnL>sMppO<aPIOeS1u%Ms}is(CGnUTagW3?lBglgaH57mzhKy)B%ElLRA;!u{k5SJPT`3l*499y@^Z#<8?2LR+~ZrQffYz2XoM$uXs{4OLZ#pq37>FkXEOs1<(3p;HA2wyS?J8aK{y7-*^0(DB7}Bth2?D#p77~)o@9VGZiv7bm+j+=pMT-tZ)0C>MLc*3xTE(-`cr5URn7|1(F}Xs@jDR@e7)^rP<QkebL<_yLF*z{{Wl7c(>$6+yr(Iawty(8DBK_n9o-<-n*}V+Q3y}+;4*89T7;0m1b~m(Mx-NnK2c@D(>sDO?67#<pW$#GG3<yDp60>|*J5#?O4nqB5W+tQsFo@t4${0fMH@E49_MDCbvlG$Tb)6uaB^mAnTMizM4g4uBkW^%9a_mifLBm;5VsE`iwCH{u2>KQ-hv|@Dvw7Y;RZYui+$94l(u_jva)8l=aqO6HLGR#fl$0A(RU|A?}3Cb4%mN%*tApGRrFGk&Y@`GE<M9fgJ=1F3kbqvh8^zPL->b~ux0`nF%-t&orP!qt{`@)kpAMzKbTDv`*}gLzBvMK0UN9qtc?d*X9Jer^Yr(~)g9t<FzjbIVV8Q8eZ(OdinYQh`@Np>_jq&Q{WF-IJ10jR@j;Y6pWs0zxUFE+=>#a-NVv|$A|820l${T?E$OhdB^}s&bTH$PILl6)kJfpCf3q_aiw9!;s*<_&Q!wa5;q~w|3$}S8sVvm9$Z=c|7OzxQM;X_8sa<)gU1fF9^8uTEm8U*}#kd05Z_IdZWw8bv2)aiUAr+@yZ|LDCuY%9w)Qwk!5M!heUl?#T-lfVngaZLATdXLtF2aKxFnIVRe)+e69g2;G@Lmy$@*IQ{HkHgW4zX_&s@4a!wnX{7oThp?P0QspJzGxUr$&h5^qoCoQOY+BjM_3z0MV9lSlTi&=>{uhhB!~f0w0;h-r%D+!>(BNvA`Fax?(W!p)nXuazd2wDxzo~%FRIxu`xmOE3cvmG{BXZ7^SUq%!Vg1`wp{hsudZ8cm+uHiwL8)8}&%vu`fjAl4RL&BStuXav%|`4_O(<03FV~LM%U%E)`p;HL61R!Zom^y`u1=f?VWDIQPeb5JL$hY@kFH1?+V)N6z)m%^P`4Mmns5fF)dk*|3V1;Y;{AGJIXObf?iVKGQoil;$9v6P?6Ch%)wQvd^%O5!<Us0HZ1-?3fd<NF@PNnTdCj5`zFQN}s2IAlRtpz=1|iz>Ky?Qmr9mLMPq%Yt0}M=Npmf6cWT~2m#f(#QH`a<!BHFZ6plZ$lkaU79!Aig~OPE#HxqGCpn^zPKfT1#*&sAOJa@1Axg<ejDp2pu&E%vbVR3AVr3_>W|L}F1_)T>LcdAR^qaI)Xe7c+>O3t7b*_OWja2I@9?SOlst7U8b+nrk*LAMVQ$qdP{z*fHcwZ1=XwI>ED7YoDDwQ}4C1I#Z;!u;sp(cq#O_GJ0Bn~x6OD#(R`RY7Mz;0etvY#qKtk+A;CLltP%8`acZJ0D$N8&)1gn=xHRlkI)U&26>#DOM>wZIh7C5bgWhuClm=SX$PMkaKqSPMbAJ_VtVHV?s&DBvNna+j96T*9!1!~qD2;{j5w!=<GTmsp1@p__k&WBfvrAB_dJC^{F?5uHLr!f_mRx3}1Uu0&kLAdDijw9j6?ph%u-mGl20b7h0bL%)$U^3KboD;f!i#HEqaQb-fJLyWW-u&EaOl)M~AC2?b%SXIQFj3aS@w5^6f7Hdys&7`i*^@7$UBehlW>Vq7Jv}gpMGlkGCNsE$5<gKHHoz&Da#wf8*Ywi$C$igI%o|_~R$CaeT+F>;?Ev*WPV@y)m6B5UlBn~J^7*LWhN+hw_AwywDA~1DG9B`bR5RC;AmIiSpi337X9RZRFcUfK_9o%B($w-kf5+re?$INg`R7UVKCseu60Gc>9Bh?#}tO}_%BNRf9-Ejg|S{WM(0X&sX2sS#Y)VBeG3|wCkqUn?FlE}epZK~JWv|MXsT}VsoLc&mxRP&E-K0m%y_iurKk-muoFQWItOFEeNAW(K2MXwS`m=8=I2}3gy2Uk=9{z<GCEeKsgz(wYS^MU|_=EMmJ5b&7LPV$5leR+wdLkvU`yT)H^*lRh0VoYC^ZT}9!5#En-*F`1qRWF1O92Sa%NY6|y>A9&TMf3v{SD*VFYLMu(CuI^;KsgT1{7ea4a#y%b5C%wMXh2$q2Bh%gr|{#a@Ove8-6!_OC-lZAbh1OUw<;_ivDtiz32Z?V6~Y<UvD<MLgu2)Z8X<@jy{HU8g>bFwyVZoRiXhAHlZq`Yt!fjowIEO<jkG8&W@W4V@HY~6PY87IEiF;$nI$R{FQr345N8ig)5tShS(ysy%+vHqnn5P;`rlS(l9;B5S7ySAhQ3&EVMsZ)O9*6~$uS6|dezpf#E}LG;|UTw`xAQI6Z_Q@JJM5l&J%jG6MC}~x~EfZ^GZvbS7KY0*quzPZZUaRZ@sprMftBqKYj}`;_DMq)LqDT1m6TA<36;2tm3T0%-NN|c59bdzaIZ$Q#*}vBhppm{mI}YVRe*alK25#z?}*aEkJL9Gpu(bG}*Fb^X~@mW3d_$h(R>M8^P+`7(6G~)E(7Mq|Z;nqo;s_%(Ov0svK@*aR59AXpjk?O%Sk=I<s}>EPgGYt#g%GLL6TVyxLMd<A9#a%~^ZrBHE`n{h}sIf;Rv*?w8tVVg!7%TrSN}T-9;=u2<b>FgQhQW-szW*~mL1tug$k*WEHyFdFl2Gy5J>IFxa)Eb6<q77a5W(TpEDLb`OuGN1O|h<d?jY7#&j^^xU-YZ3kfHgeOsSXq@=bPfV%w5%@NqS>jbqwtBG=3aKT0_@Elx$WKT&K0!ciQj)==cY0r(X^?EC`dRl>~XlKED6KY93AXQiQuw~VdJ059wdN8tl6bB*$rvR5w6+ECBTje@!WeG($~a`W2!n`pbeQrEAtz+kSGVCE$CK06Y$lmgwZ$HOvoX2qk*!L3Xhadn`$DG$=2gZ$>uSG2*jV4<1d(^ESLLAQ83aGQ;0f7K27R-F%G9YcORgu034V)r+=f{WfWfU`8zlkilGsj02iigYr0&G1k7UxkAWB~BS3RH-(;D)1lZ`83t}<Mq<@QL$Y7EyuAK|tq7#^<WCkZ<_L;DRZwAh~c!^NepAUqW0IxAN8)Aktyy%kj=e^rS)VOuh16|y{|59L|kUHV{HzzoI^g6D(jGQ1kW(-EnLuMfH>kCp%=%HgdATW{%lKG1dm@N}F73Alw?XQixLEadCVKa<Gc|N!XUuqk$1RAJn&vS$@+@?af_)znT-bfVhi2y!r)Eaw4!i`6C4<ctkTMk>2PgO(wYgLM0+^WmI?7@;>U<J;aL2T=-2$|a3oil&6m#z(zpx<kOjfiJngvbjn;0e42xPbtcA%JqDEPCHy-!z6cGOJKSnXRym3ac`!TNPTSRjoN~@!K7h0<^Ow+fbrR1$~I5#W<=KqmWt*)oC#dr)B?F3-{6g2`E0FmhXYKd?B%|?;y7I9lW-_f7bGSuC~6y)#4qMmM?F#c>AKo3lJ?{a%k~xLyJ+Uc^2Ad;eqY*Fub-7#A_+)403qnRa*zaw962d_IY?oTgNrD7TM6&UilU+@$J%H-ny-s+L>^)78aRysqnX~dA2P1wk+(nEW5T#>8oXNp<QmKHuSd^m9;jsj<)QmlGs}kT5&fTXwxm!Dg&r_Y?DV9mB(%4v3&o>lSJ3@j4Qf&-5LXEjdPWR<k^;;C|1?$O5B-)?#69t0<aVRgia?r-ZNDyc%^<<x^`zDQ_@6<wD0VwTA}9M#g`OF=kD^%<v%@HeV$y$Ug3n9=Ddrfv;Z`2(zZ#{KIU;f**u@}2GOJqC#cq^_<q#M4ylzX)VcTP;%{29R(-aYK(#)b;IWdph?zfuW_{KN)`YVflipUSOP|Y;dMTM*Z`MT4><jr4UnC+e8Z_vORd%uO4?!|s6!p3{p0GkaxsQSBi$zEBhUN@f^Qu;%-^-j2CXq_g5-vD`p8Vkw)DFQs*|Vr<WsI??L8q3B^lJHgm1o9gMvDtxp`JZP$9(UDsy*5nIu?t9%A7f|jtRfU+JOKkXJI#sQCh_rTdCuuir>p>S%s?YYPKKCcbn48opcz!jOMyE>D7}cw32g*6$*;AoIdhrk6f!(y?L?*x$^9avnO*mJ&APb8!>WFp)J|vl@eg<1qj>`;AeXWk!`bLy&QD%DfXQT5t9!|tVB@AK^Z4Se9ElGHSuq&_q#ZC^%$0NzeQCmZo3)VZE8(w0{-MnP_D>p!mbn#M!0HXZpNG_mrbRFt=xs(8{ErJK`*v0a<a8V7YWZdH{iuLych%}A-+aW>cFY2QvT*4D+xIz<TkS%le&l8B%q05p8ADlzz<wY_>1zTK~L@=iCOlR+}W#J`|C=n+4h^i)3x&Nn#svzAHG`o*P|?vtF`2AMW2ZBuR8g6jo@29^pP9-jtPCnLO&;Qjwkkg1CV%0+NBQ%&^>>+!4J31;jXz0!hFqmrB_?&zNcUD9LpF6%mR$US5E{Da&L7&vm&{QOQN2Pmo(qbn%+P{KDJn{>aF0OA6;^zn`U|gt3)9hD8qR0phCKSrPr%|#S@F8qpL~+KJ)~sZ|<z<dJ0|c5b&k<W9^=YXohr0L%}^-VX7G2SkP+&-=0m4b_&etO7Y+n{;gmaPfEaczrs-KRfJEMJtOmG<~cp2Up!&7wiHuhl`T=GKjMrPT&y_}8C)6m%&4b{GRny|T@ggxc+#!R<mU-%^f?+B!Jt*NrU~&Y7j3E_N99}lm4+xLYff1bTKxwmH!Bsd7O{Ob!8S%Anhu8HcD7(RBFzb}8aLrAbz=o)#rpS(0)t$1w}j;t6J{j$E3#vHuu5r2K0H=c*oK;;H1Aq{<@c2_c3;r7D(Py9`+9A07^6wSU6QY<U@0kBN-~xraqgCEbRLYm_=7!6rkxN;oTTQ5jUMeI(PVXF1@1%g6@pp|t`l%Ym{z+|GqYHQ<0F~^<8zS?drQVKMBfxt*h^(@l+omeauEMmlqc7^t*g_C3^5AhB&v=dI)Lb_FA87d$p-1sC_SF&vls>;zmJbeM{D}#g2P_9NX66XimAd8n;Lf<71|v|gU;sZmK;HC;sLuFmwL>H;T(~SH4JrskcY$k8-5!A2x}x@+%k}Y4?!sGNV#lz7^kRMK@}0EgnCm~)*&TCT!s+Lk|Ka6BDN51BHl)9G0Fro5Q$x|I8pMSw0);$5LqkD%HCL!T~-Wj<0>TLjs7?)OAKIu4qQqC|H*&Hc=>3FQ_#YT10Edo&#WqE4LD=Mw^Fi|nDafr5dYc5Lhh9rd__{#LjmMaQP>gG!okfVp!G%-VS5wE94p{dA%_Y$QzDsJKY%F9yei~TF;GN+aIJt_#a$}kJt5CYW<EY)1#jh~7p&UG#+J^?O-kSo0bj_D0A+)hb2VFC1oJXgTmMR=?M5Dk2(%Rys<8|X^02{D--RZ)ldp{DzucUi5{-52%0VlCd02MZK9PPJ{l5B~08ZGTz}p}fZ1i*Aq9bFlzJ7e&J~r*}Qh_{g4SiJFU@4wItn36oAe-v5yFmEB;_NfD0i!?ojaP>~zH47zMM7aC&Eg}cK<XKO2Jln3S$v1kNq#gpl~cqBaXdHGhuMIj47Z^#lR31w*&twMi+UvjK`3g2E!$8r_>O(D2nec`Ht?|@1@ToDC-_O<R9}|}f*t-%<*um-ID@p>`F?yw@V?;nYbUvi);x9UIC;-wnLGg(MV;i5L{m9_Y67-}uQ@&=MtksbqLW5Q!lf7^qI}Rii5Y)Jgc_mmC^9q@XV*k7bO<P^n%A)QD!~PehC-Yax{%Q<98-l97OST6{VRb4k;Z+Om$I*G-=L6so9osRu3$8%U^Mj*RNcP>o271>nOmIMz8r3Ld^FhWFr3bh-EN7FZ;3?%n_FYnq$W&1O&E2o5<8Nbuo^Tz6?SBX3%wf05Ya5zX+5FYG$GVAcnI$8{M>_M%g*b4oT>XFuKXWu%A4^"""  # noqa: E501


@lru_cache(maxsize=1)
def get_core_lexicon() -> frozenset[str]:
    """
    تفك ضغط المعجم المضمَّن وتُرجع ``frozenset`` غير قابل للتعديل.

    النتيجة مُخبَّأة (استدعاء واحد فعلي لكل عملية). أفرغ الخبيئة بـ
    :func:`clear_core_lexicon_cache` في الاختبارات إن لزم.
    """
    raw = base64.b85decode(COMPRESSED_LEXICON.encode("ascii"))
    text = zlib.decompress(raw).decode("utf-8")
    words = {w for w in text.split("\n") if w}
    return frozenset(words)


def core_lexicon_size() -> int:
    """عدد المداخل بعد التحميل (يُحمِّل المعجم إن لم يُحمَّل)."""
    return len(get_core_lexicon())


def clear_core_lexicon_cache() -> None:
    """للاختبارات — تُفرغ خبيئة التحميل الكسول."""
    get_core_lexicon.cache_clear()
