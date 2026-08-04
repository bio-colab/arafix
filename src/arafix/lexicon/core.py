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

# base85(zlib(utf-8 words joined by newlines)) — ~8KB on disk, ~1.7k entries.
COMPRESSED_LEXICON = """c-nPbTVm?E4*k!pc?7bVMd8o{3Qbd>G>nAK=GuBLIoywPc6lX^ElW#FOa5Cv+v@rGm;U)%R)5VOz25Ub>8<DXZ^eJ?@`w6o{T$%kzkl-LIXr(VdRKn5|64sT>96#%=ZotPFLcYAUhpS>oAl|CKTUr;&*}et_57fhAJ0Sew|@RdFW&TapU=VWoyYXI`CFvR9I9u>w}1Yme`ooP{Ia88_xkI5`lQuoqA|+7Wb8UdzM|YQy%_9e`Yip5E-R1yw=RCnFGqSYrw9C-`Rwk}C$$e^o1dsk*YPi;TQoXn_TJn^{X9L7`3mVeFv@GXPW!z1C2IY1k!Et3%-D;I>325#5M5e78h}1YT8<gNfT5?WskNkK@6yP}FmV;#<(wxX8ChBYx|WTaEa1&&#tdsuqZ-&gc50<O&m+!rwzp#%$I1+e-pI4j@#N<LjL&Ye#8sLHyJ|MSn=K1}l5U|(?5me-J6*zN{zkt&_-^Q7_oOf1;c@cy)b7EaHn!MlmS_~|BJ_>34z0@TpQf6IyQQzr{P9ouv*$OO!}-~}S<|HJ1hl?C^MlrW)wD%;?coCUC+_`4n$@(ZHE$f>m7VYNoh?neQC`9Kd=I_!$Y$qrG^GDJ{nWR9bSC(0>C4II$nR&kQ0}hMpf~oAv}(PMX~?VTvtd(S(Pn+uosB<E|33#0;KSL|M3a9Im&(SXkBOF)Ei&DvW)lcIC(S|sa?<oZ+30FtoNs&td+ZBuHaEuh`J*$tCpSh@`NG;N_mpPQy3tnt;Bp_gOZg-%s}E?O_YdvK24^Y_EcqIaI_4@%TN|_cHiwY>&5z!*@EyfXqR%}9EAY#ivH9v<b@h0NANgWvHo@~Z?zeY;Yqn`OLHW&h+8j23n;ZU)T)@KOWU`mWXBU=7eyx6s$D>QjQzF49?|h%C!6RL<bmrV3+)mx*nnOW;67jJ99K9~?4&S}dw(sKBh54@81jFNmnelZ%?~7qc2Ul|_A!qD!eWCqoE3|aabD~?n`2(j3rl&K%$NTY8(a`c1oVia~pf_9NNEI*0uM|+E>&@L+HxWl|X;uapWprtKo=AO5-8J6=Lb*@gkiI_#EAu%P`x~-xWIKT;Z6-L3Y-pX_$)SjEx)6gd-&(gWjsRjeMLu-XcQOvx${8!nqj{gm&DnOlrEARbqGTlg4UY8|J<>oa()UwXc~C!g&hyzw=w!QBz?L6<h29{?v7fw7-RsaAARXJ{LRaucb9~5iypLGUpD#^x?~yxQg^WiW+Ni-N8?5d>x|4@!85kKWc+q@YM|!;d^Y`<ZcRUXsXlk6_M_97-yuZG^4QIInYsf{-eUI@oV<1GUzF|1ZoBv3^pG|NY1PM$o;PDnT5CGj9HSF{Aml6g3u(8C(A^<vVg0ybxX#^1FZ~3d3j-0Yn1XIf(j4vj^GJiV8ajj^}(N8f#^0xA=0rLR6-$OlMhVN|Kf`Hk-hkygi1Xux)c<X?9pH@5o@C#WAqz89=iFu%3{ulE&w&RWau8`^s8GiseCMQ`V>cM1y49ahw-nhGMuJH-?F;L4I$ZYFW<u6~<FcdwfM?ABY@%IZW-H}UapI?@DrO*F)>X5>By6}JoyG%d$#$<tvQ?j1IJ0cQ*$(>`EVx%9IGw&P#*sW%WpPC80NL)jfu#>OOeIGQqFc-V@Bt=fQ{>59b@;<;Vb)q*dG=1k)o`kvre8(v8?IzKOJxDiOyTcm6-(gCaqf1NHb(kc&ZY6mjb4`Uh``$&}Z6kivV2$AP{PQw#ec)r|=L}HJk``b76T<QnJ(v%SkTFdAr;;NYvL{JDCc(*v9^+znG>e^sw}8of2d1z6ILP8{UI%xaX5vV{f5$h4slm5C*+OJd)IYB5MUIpw4P_x3X$;j({05m+WekZ-gzztV&m-ac0ev)MPTwiUBBVb@rZm*PwgAp)fBth`V(nLzFdhBtQFC4l85ASJ{R6{M#)XwzRfqY_y$oTCm|v{HVWSnU5OI;$pvUiZE;fD{qvjOMSiZWPkaP63k2od)Aey<{>G49cTE?VT`C9urQ^dU%v*l4NgsovpB5rX8n4fAqz;|S}AO7-=`J4e%r#i^S0~^S6jZ%)q<GXiW0gEL2P^|ksUG{+PXQ(uaD*gE)TiXdxwP)K;*ixFHv?{W}ve}q}2-wBKso@6z&=K^axqt9h!nn`@K1%C1^Z4zKmLFQ^6J!7&jQ{`!d^6Iny0ytyfp_HbUJ=rsBRJ~FdyPKqAMk)NYh$Knoj<Pvv!ggulRjZ_HkxAZ#2K%vS7>Yp{Oj}6AN<?w%pbaOGuo?zLDXa66LX@aF9JAs!3I41eO?iQHL{=TOeHkPK&uzrAZ>6K$X>_zD?Y<rmh90PY&=Y=?jcd6;B*FZEpsw%=RH2~7x}ROgdm!Al-tQZ8F=aQ(AJ^2!AQ`SV#3`yLuSwm<MM{0Z}jra;pb^PGpd}Wfq!G3soWKF{S?Uqq^6uQgyj!UP4<kFF}j8bpTdeP%)+=lN=rPq_h^cAi06IFkoYnT;yF2Eu3|(IPQaOSqc|&p0;UniH?%-uN!yXPlk$#feiqT`ZL{x2Ga7)6!u>U(P3$p+$$O;)S!o}GPno%WtOOm58L|M8a3tI2S?KeMTe1OBRNP074aWHregVQo_TIw4jDzi+<S7=KdZZH}4$N}GhN1UVB+#)a(<XpN*`^dj&@~tx;yBZbQwluGlEl8Gk8TMIdu33Vy3$I0M~yLkXp!ROn+?%lADN=flWjTN%<2yl7RXssiK{?s(i>h3Dd_F=9ACI4HV!qR7!`w}yp<xR{qRUAbE77LE-ElsG#D?2kTI?mDXSHXSiF=JE)q7`WG@gt0Pn@hrA@tlJ~EM<2YFI|=_b`zfq$ma?tz$q%B<NAm4chHnybm^!4t-B^hH<R_r95(Gp3inp02DYbQrA>D><|vfs$%tff%Ertc`9F36zc2T(`jwq3_&gax^B-KglKhbG`t;REy>6wkW`4pKCRnWA-aEqyMr|uzfGQTG=o_;zH`gEoW9~L~?%Q-5BydgsqAQY^NdDDSM}=q#6^+!+BASHBPm-Z9&Ty0r$l&1GB|)x!vd-C?5>|3rC*hRjab7rhsTI;W5<DfmM`8mPk;^v!6A7>@o+1hI|1~o$TozGt*EARf4%D+h1jrz`0|mBo&%QOq;i~`HbZWh6t%=dP%#*5e7Z*aS}NuDI5CUvtJPN48qAYq6-_UTJ5{@YQ^<-5wYyC+*Ck@04uCKp1ypQ#Z8}H9a!lWSybZ2*?};%Bz`RjQ_{Q?b><y;a7>RdquXcZBEE5B=okrBi53rqYTX2^rR5$3@w_>AG%M&bh^Bc$U6)}r-CoLlCoj`5lo<m^r9t+AsI6>x68#tY$HogzE6qtmWR;{2UHq-Ad0{<WC`e(iSHPx8bQ_}j;~dTRiWM#bte%*MQYX*n!(B|FXfcY{8RFWl*34QHy^bCqMM%vHZ4ph)UGbt3u7O(e;eR=`bO8YqUEqT0M(?|^apI;_?GSx9qsVnYa>2aTOzbgo3=_f5$!B|@tp_YP6FObQ*!_eBMusQvud_#F2xy(_tU70{I}0WRYHP32W$a~@@~s20K%Tm1$>ol@vk0?LyM1979t6v(q%yrwcy<TW_{OazAzQ$+WmBnhsn>jXf=C>&saUa)3tU1K0KgoU167$2Tp^Img|<%8J!ZhII+gcc#G|q#N^6ml=Nz~2rL6sTG0dGXw`acItw`b-6uok8GJ0iw4o?eZ6=2V$l!}!&a>q5k1v;x^P!@!$Aabm3T1|R{-dQ*BVM@`}00yH!*%3|(BzBfZ0Y-0d*ROp0+<=j1+=FQy<umT+d-q)dIRNdG>|=;BFrzkM%yG^*zTPoLyi*Nyh6KwO@_e&$$Ja{eFSBi3bT%}-5sX`vvNNIjqPXTx73Blg19zU<d^oCJVGU|ek_F2VfEB9>SOw4NNEcOxEvh3e5)@m?rKQG{c4`7=^IJJl7xP(L0iPUjCG^FY+7#*tB&j&MGyBBi;|00Q0lBQa;$KDaLrL0cO`>yf1Bi`7VW@}Z&Hhjy@w`@wxw1O$==7E|RFWC`1A{11p4Sv*TZBnliYOfldpFT_WK#s=nE7V9;%1_)<REH|j3p@{ye^nijE?4qOfM9=BGY^<z*NZ1b;;dCpw8yFQ^cpqtsezk7%M^kD(F?Lz$F&B)4AGnz(gP~B?xz=Yb=~MbX{OMyI?n5^AGw_9`MBBMxN{lwIzBP<b~`YYW&VB+Hb3hIiA2AH*RWmmX_y);y;a`O1S~S&<FU=1`~xUUQ5N?cmNEMAv$Kp%Um_Vym(RSX+s$l-x`r_0bMGTNcD|};NlLa@Cf=C^{{jw-<)BuN^A?DPpaol)Cd)tvN5t{Di4z6*GRvp$|B&~qu~1(HO60og^fJGBk(w~;KvE>@>xgllS7~uNKA=?7J8NP)1rJ+=tcykY|Z%1sn)V~5YdaO<4^@urP5=j6FyvAzL(9;g%*>OXa&4N(V!LQK#}A4M0bSeq)TUk8&pltu^1OBmB_>zRG_p4ZG1tO>%Gqa<flj;_o(qJL=f$Z(g0O+-_gp0=9SoHE!lr#g`yRr=}X)sChpo}QWWr##bb8}d8vYlYEaqKqbwg#P};|+_iSA&-u@pcw$aob7C%A1dbG^pOH(1QdWMRqnBGpdt*OOn<B7EZF0t!4c`H6($@q0ef0Bt!>0*B?6jGeYZ=o7XLI#hqQKGhw`Ct)NefGuxC2@I}Ub@-mRvQs?xv}mCQ*sJoE~FolQV9$(8RoLk)npm1)(jeN|CtD*RM_%?D(zCIJ830}xO_zH@PQ)3m(gibN+@J|`o>x3P{V<+b_@l&vI&V%!%bNo)rS*}tQUDjBcCv6XIyp+YQCb`C#uNU|04B~wif3It3sI-8VgLU)xhMEe*54)Y`_+SI_mZd<#5oJnzGc|afC*^SZ%<nC-2z;cZ%;?6j2n)$sXH&$f0;6&rTf2fO`qLvkK`wBeZj<dk5zY^FXwMv8YI1sY$p>n6%qn+1@m$2&tOn2Qeph+{IN4W&BZ7)l8`2Jk2iCQ+#`L(KTz10ng6UxBj7~_}k~<4tU40s%<7LHuljXCj1;f>ISiNJ8dsIdGv?YDeW-4^8}v+6@`|S0!c}*tBqCl^e8kP)xI1^a9epri(Ib?vQ@13?S#63_!sEaOVsOMU9q91HOsIcG16Pb-&ry6<2_l#2~|z4bxGzs9yQ3FJkh)$%#!EIWHjWXu2A9r2}_Y^TAQ-}3fc~Qn~unmWH0zA+R4)RZ>R!s(Z?O$3ZV-XAkcdn<!DmcWep=?Ii}h@bV^goT-bPPu5lWQx(Qrl)0CQ~lG#qMBIrbjIh{P|q#Fvovq?a)<Ki<ia{GxYxV&*2`|m)7@FIcC13cw)%lFhxcx0$JuH7AJ$BJu0wXEYpURQ#tue8doPY3VpE(o!mmYk^Y_Stx1bK(`@@w-&CR<Q^JB(J(#@Gy=h&yJZXd&IEpV3{m!rgQAu>`_4rZ49)PbqOjKK(fYr;4(Is!ukfBe>6X-Cp22BoM<pvp&AM~4=k<Ck%Zhu3}Ln%L~mS;z)3x0<<Q}w2`jA;GSvHFIo;)~byKoPO__aZqcX1xDv~BP)o!I!?`17_lqAkW9wF)zT-OzIs7@!ZgSfR&eF<`|h6B$=av?1A9K#Fu-bBQ;h_38%Jy~fLr-@t1=Co&wE}vWIa#E`)y66lxyl7P3M#H(VSSGUMpivu38tecyK<f;_c#!36H<7QyKJIa!?!C2^oqt{8^UzJ*mc4Hoecoxajvg^?C<r#H$A`?5cxUDJBNEM23eAwHD`jGUPVSaGN1;wr;ynu>*u^gWC`GR;$TlM1&;(9Z#JywDlo$Cjl-&w?7$)%(c6CUT+yy$|Siaa2g|J5uHvRdfsc%;vyU@Mv<~h2&qn7}jTkOb*N~t_1qX(^~U8@+D^2L9}2WnobtkBBE#7*pn_kgvjid?<q)<&d%_F9sP%8t-01p1lK@*#Lk_3ATdg^GI24!bYB(y>7oAze=cliUmKyDE;t@Y1_Qm>%7Rwvr1{JYZ!FQpQ{in_*)9QjE9ft>ZhjBmWt-wb;mYcI+6G>UWI3HHo&HDKjhZyL)*Kg*Ql70u3ciSg^)1gTR`b>%12E?E%LQ)M$zZIp@PU`O;R%AZUN#+Fl%X!i`KO1EBQi<e!o}-Q8x<q%C09cfH*Z_x)wc0)3WE<R_0?7;t1_t(>H3XG$%9z225xeoq)EoP=S4apn_hpEcf3X5N-34O%DAe|}&i$tB7*vB*hb;Rl0SLkb|U&=dPse2Zh&TZmY(t|uzz7^FbA-Nwe(cG^rpn4FwcKT+4?Wk&_-zD>q>n#fP6DtnuK7f*HR@EnVa<}H<0941m;g&dA<a(P(u!p^9P8;GWnjp|XpGQ?9mc65XbAk-j!83`=(4p>{1Ddzh85i5)zq$$8PEk)BJc!SNrV8%6!p<9EcAQxc|{PCl%-rCFFOscC67c@WK6-K$F#i1s2YPc(wGL69qY-uwAjQr8DY#+`~0IU&vVcO8v<fv_q!hMY4+WQf~^H5snr%;Y_=zK1EscFJcyfp1+YvU0wZK1C7b0tF09<bKx_u<@)ZgM&iCbKBHcka?M{OFmHG)8$D);CpiX8-{u$t_a(3j#+QKM<*C^4Z6PO6mR^0ywE|;z~T2HG$4ysTrT4cPJbIR94^Kx$Xf+d5A$!Be!cVF1lh0#wdxKD`&))npfVLApoVas<hRaq+fq&eON5SrOX-#C_ehe_CzsZIgViGI-&PjI3p$co@*33j%dLIy|Ii(`Q#)!HjW}{#_lCBKcTWgPPg!l-IR^JqwLYzS2dg%v=H6l8-i}lXA^v6zwm{7qgFh*az3#0I#<z%I&;V3esHA?dCCL`sP_K6$dpRYxn`zwZReTnFA#Fa3PnrJT*Vuk<TOG$ic)rwh5|=Mng2`1(CgK)hJht=6Sa1+{i};dxPbU=bkFPOAsF|#_I{2A&V<SD!wYmvdPIQb?;GdY;t4vT*eL4nAj;LgyKvN74Sjj^zzv=o2Ip7oOI4Z_tE2z%F6}}x3Dg@L7SzVGPgv2pio(xTnXb#|uY|1y|8s{}hF<?^F#pwdnwe_>=&%?As4^Gfq^8g{6V8V*ZLly=t!uTlT{5V!R#j*=M)9d{fdUDHI{2Oo@a}R=2paSsWY0gb&2yMA?VdcWxc9R_xl!o&hHKtoNuuZ+19TA&2<oMo{DO`RPNit4E*Wz$j8LIX2z!SgkZz=@pJOM9c9|P4Vq_sD5JF+LOih7CZ1Y(=N>d!~<-pAN?%Yha(F)5>9ffs+dF3r=r$JjETg$E3j{&L1o>^?;NXv4Hb=kh$ndO-uSlJFb9fVwVC<<yRGV-wiuZZ}<j!D(M3!V6HmnZ5ei_!-oJnq_$`)dGofV?c69ngF2J5S>|9=7-ak_z;5Ur`U;#dAT%&<Y3VZ$Nv)36r#a*+QR#;)k;v0k)ZbXVSeqS)}wppWIPU)IE{<G42dRDKtfAFT3<^o_J7MH0pS0P>>eM;`Ms|Sv-6I$mJ!H@z7S;L>-MC+s7#g5bl9kDmZ9p3Xd8ntKP+Iufv{P<GDS#SUaM+`82}$r=3Nii<<o0*foL5k|WJbGlj)v>3M33qb>lz)<J0-UWDflihiXlP&+l2LQ`NRu2FQpXI+$^0Txbx;<dd-P;`kR(i%NPc`!vhkgSNpc!Z*C<j{rGVQ&{TeNV;ND7hhy(;LoEJ+e@#Tcu4bO>yL-cK@q0-XZ|qB1<M%DX{V=G`S!*2Q`dy)b?8uJ8Q*Gq3o3%HuAOvucfbC4=<2oUMaj$)$`4oqXbG$PT7qdI5T(0QqACz&(0E-sbPvNp2oGMhdhM#IB1_y9W-*1=Qu03cp6VQ5481DE!#rOEJ1mNmbi!&h=+~~iUmxL1$q5USw|;^?W9%nc?7$B@;Bbe?tOhKVUqO5<bk{`kUmghJ<y!r@eOaq05bU(3!XWwTzQnv2du#hpkxxh9Q3A^31KUE8&9Y5Y<d<CF^C5N#G^*rctmGg9IS}Pr~p|Y)TNVdU3oBQ2lPzx&CBv^7~v$td}%JdP!4|yn)wSxtq?M;9_444F^=rwX-)&i{Tasn&roPqwk%2tKhfI3*<#X(XEeGN0kHvU8faLf9Q1m8(GFPF<YlJeoV||R_R&w&7{f{940tleZUiP+r|%pOUN=N6l)r#(m>GNOALmxZ9ZS83X8c}Z%gPcDZ&}83i~k2cKCv<"""


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
