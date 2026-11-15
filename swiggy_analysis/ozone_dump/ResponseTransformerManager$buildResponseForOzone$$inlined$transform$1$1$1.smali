.class public final Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1$1$1;
.super Lkotlin/coroutines/jvm/internal/ContinuationImpl;


# annotations
.annotation runtime Lkotlin/Metadata;
    k = 0x3
    mv = {
        0x2,
        0x2,
        0x0
    }
    xi = 0x30
.end annotation

.annotation runtime Lkotlin/coroutines/jvm/internal/c;
    c = "in.swiggy.android.tejas.ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1$1"
    f = "ResponseTransformerManager.kt"
    l = {
        0x2b,
        0x2e,
        0x31,
        0x39,
        0x3b,
        0x3b,
        0x3e,
        0x41
    }
    m = "emit"
    v = 0x1
.end annotation


# instance fields
.field I$0:I

.field I$1:I

.field L$0:Ljava/lang/Object;

.field L$1:Ljava/lang/Object;

.field L$2:Ljava/lang/Object;

.field L$3:Ljava/lang/Object;

.field L$4:Ljava/lang/Object;

.field L$5:Ljava/lang/Object;

.field label:I

.field synthetic result:Ljava/lang/Object;

.field final synthetic this$0:Lin/swiggy/android/tejas/o;


# direct methods
.method public constructor <init>(Lin/swiggy/android/tejas/o;Lkotlin/coroutines/d;)V
    .locals 0

    iput-object p1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1$1$1;->this$0:Lin/swiggy/android/tejas/o;

    invoke-direct {p0, p2}, Lkotlin/coroutines/jvm/internal/ContinuationImpl;-><init>(Lkotlin/coroutines/d;)V

    return-void
.end method


# virtual methods
.method public final invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;
    .locals 1

    iput-object p1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1$1$1;->result:Ljava/lang/Object;

    iget p1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1$1$1;->label:I

    const/high16 v0, -0x80000000

    or-int/2addr p1, v0

    iput p1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1$1$1;->label:I

    iget-object p1, p0, Lin/swiggy/android/tejas/ResponseTransformerManager$buildResponseForOzone$$inlined$transform$1$1$1;->this$0:Lin/swiggy/android/tejas/o;

    const/4 v0, 0x0

    invoke-virtual {p1, v0, p0}, Lin/swiggy/android/tejas/o;->emit(Ljava/lang/Object;Lkotlin/coroutines/d;)Ljava/lang/Object;

    move-result-object p0

    return-object p0
.end method
