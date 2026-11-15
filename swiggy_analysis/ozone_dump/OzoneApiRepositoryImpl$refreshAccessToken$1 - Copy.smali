.class final Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;
.super Lkotlin/coroutines/jvm/internal/SuspendLambda;
.source "SourceFile"

# interfaces
.implements Lkotlin/jvm/functions/Function2;


# annotations
.annotation system Ldalvik/annotation/Signature;
    value = {
        "Lkotlin/coroutines/jvm/internal/SuspendLambda;",
        "Lkotlin/jvm/functions/Function2<",
        "Lkotlinx/coroutines/flow/h;",
        "Lkotlin/coroutines/d<",
        "-",
        "Lkotlin/Unit;",
        ">;",
        "Ljava/lang/Object;",
        ">;"
    }
.end annotation

.annotation runtime Lkotlin/Metadata;
    d1 = {
        "\u0000\u0014\n\u0002\u0018\u0002\n\u0002\u0018\u0002\n\u0002\u0018\u0002\n\u0002\u0010\u0002\n\u0002\u0008\u0002\u0010\u0004\u001a\u00020\u0003*\u000e\u0012\n\u0012\u0008\u0012\u0004\u0012\u00020\u00020\u00010\u0000H\n\u00a2\u0006\u0004\u0008\u0004\u0010\u0005"
    }
    d2 = {
        "Lkotlinx/coroutines/flow/h;",
        "Lretrofit2/Response;",
        "Lin/swiggy/android/tejas/ozone/a;",
        "",
        "<anonymous>",
        "(Lkotlinx/coroutines/flow/h;)V"
    }
    k = 0x3
    mv = {
        0x2,
        0x2,
        0x0
    }
.end annotation

.annotation runtime Lkotlin/coroutines/jvm/internal/c;
    c = "in.swiggy.android.tejas.ozone.repository.OzoneApiRepositoryImpl$refreshAccessToken$1"
    f = "OzoneApiRepositoryImpl.kt"
    l = {
        0x14,
        0x14
    }
    m = "invokeSuspend"
    v = 0x1
.end annotation


# instance fields
.field final synthetic $requestBody:Lin/swiggy/android/tejas/ozone/b;

.field private synthetic L$0:Ljava/lang/Object;

.field L$1:Ljava/lang/Object;

.field label:I

.field final synthetic this$0:Lin/swiggy/android/tejas/ozone/repository/b;


# direct methods
.method public constructor <init>(Lin/swiggy/android/tejas/ozone/repository/b;Lin/swiggy/android/tejas/ozone/b;Lkotlin/coroutines/d;)V
    .locals 0

    iput-object p1, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->this$0:Lin/swiggy/android/tejas/ozone/repository/b;

    iput-object p2, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->$requestBody:Lin/swiggy/android/tejas/ozone/b;

    const/4 p1, 0x2

    invoke-direct {p0, p1, p3}, Lkotlin/coroutines/jvm/internal/SuspendLambda;-><init>(ILkotlin/coroutines/d;)V

    return-void
.end method


# virtual methods
.method public final create(Ljava/lang/Object;Lkotlin/coroutines/d;)Lkotlin/coroutines/d;
    .locals 2

    new-instance v0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;

    iget-object v1, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->this$0:Lin/swiggy/android/tejas/ozone/repository/b;

    iget-object p0, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->$requestBody:Lin/swiggy/android/tejas/ozone/b;

    invoke-direct {v0, v1, p0, p2}, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;-><init>(Lin/swiggy/android/tejas/ozone/repository/b;Lin/swiggy/android/tejas/ozone/b;Lkotlin/coroutines/d;)V

    iput-object p1, v0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->L$0:Ljava/lang/Object;

    return-object v0
.end method

.method public final invoke(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;
    .locals 0

    .line 1
    check-cast p1, Lkotlinx/coroutines/flow/h;

    .line 2
    .line 3
    check-cast p2, Lkotlin/coroutines/d;

    .line 4
    .line 5
    invoke-virtual {p0, p1, p2}, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->create(Ljava/lang/Object;Lkotlin/coroutines/d;)Lkotlin/coroutines/d;

    .line 6
    .line 7
    .line 8
    move-result-object p0

    .line 9
    check-cast p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;

    .line 10
    .line 11
    sget-object p1, Lkotlin/Unit;->a:Lkotlin/Unit;

    .line 12
    .line 13
    invoke-virtual {p0, p1}, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;

    .line 14
    .line 15
    .line 16
    move-result-object p0

    .line 17
    return-object p0
.end method

.method public final invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;
    .locals 6

    .line 1
    iget-object v0, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->L$0:Ljava/lang/Object;

    .line 2
    .line 3
    check-cast v0, Lkotlinx/coroutines/flow/h;

    .line 4
    .line 5
    sget-object v1, Lkotlin/coroutines/intrinsics/CoroutineSingletons;->COROUTINE_SUSPENDED:Lkotlin/coroutines/intrinsics/CoroutineSingletons;

    .line 6
    .line 7
    iget v2, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->label:I

    .line 8
    .line 9
    const/4 v3, 0x2

    .line 10
    const/4 v4, 0x1

    .line 11
    const/4 v5, 0x0

    .line 12
    if-eqz v2, :cond_2

    .line 13
    .line 14
    if-eq v2, v4, :cond_1

    .line 15
    .line 16
    if-ne v2, v3, :cond_0

    .line 17
    .line 18
    invoke-static {p1}, Lkotlin/l;->b(Ljava/lang/Object;)V

    .line 19
    .line 20
    .line 21
    goto :goto_2

    .line 22
    :cond_0
    const-string p0, "call to \'resume\' before \'invoke\' with coroutine"

    .line 23
    .line 24
    invoke-static {p0}, Lk;->e(Ljava/lang/String;)V

    .line 25
    .line 26
    .line 27
    const/4 p0, 0x0

    .line 28
    return-object p0

    .line 29
    :cond_1
    iget-object v0, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->L$1:Ljava/lang/Object;

    .line 30
    .line 31
    check-cast v0, Lkotlinx/coroutines/flow/h;

    .line 32
    .line 33
    invoke-static {p1}, Lkotlin/l;->b(Ljava/lang/Object;)V

    .line 34
    .line 35
    .line 36
    goto :goto_0

    .line 37
    :cond_2
    invoke-static {p1}, Lkotlin/l;->b(Ljava/lang/Object;)V

    .line 38
    .line 39
    .line 40
    iget-object p1, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->this$0:Lin/swiggy/android/tejas/ozone/repository/b;

    .line 41
    .line 42
    invoke-static {p1}, Lin/swiggy/android/tejas/ozone/repository/b;->a(Lin/swiggy/android/tejas/ozone/repository/b;)Lin/swiggy/android/tejas/ozone/api/IOzoneApi;

    .line 43
    .line 44
    .line 45
    move-result-object p1

    .line 46
    iget-object v2, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->$requestBody:Lin/swiggy/android/tejas/ozone/b;

    .line 47
    .line 48
    iput-object v5, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->L$0:Ljava/lang/Object;

    .line 49
    .line 50
    iput-object v0, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->L$1:Ljava/lang/Object;

    .line 51
    .line 52
    iput v4, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->label:I

    .line 53
    .line 54
    invoke-interface {p1, v2, p0}, Lin/swiggy/android/tejas/ozone/api/IOzoneApi;->refreshAccessToken(Lin/swiggy/android/tejas/ozone/b;Lkotlin/coroutines/d;)Ljava/lang/Object;

    .line 55
    .line 56
    .line 57
    move-result-object p1

    .line 58
    if-ne p1, v1, :cond_3

    .line 59
    .line 60
    goto :goto_1

    .line 61
    :cond_3
    :goto_0
    iput-object v5, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->L$0:Ljava/lang/Object;

    .line 62
    .line 63
    iput-object v5, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->L$1:Ljava/lang/Object;

    .line 64
    .line 65
    iput v3, p0, Lin/swiggy/android/tejas/ozone/repository/OzoneApiRepositoryImpl$refreshAccessToken$1;->label:I

    .line 66
    .line 67
    invoke-interface {v0, p1, p0}, Lkotlinx/coroutines/flow/h;->emit(Ljava/lang/Object;Lkotlin/coroutines/d;)Ljava/lang/Object;

    .line 68
    .line 69
    .line 70
    move-result-object p0

    .line 71
    if-ne p0, v1, :cond_4

    .line 72
    .line 73
    :goto_1
    return-object v1

    .line 74
    :cond_4
    :goto_2
    sget-object p0, Lkotlin/Unit;->a:Lkotlin/Unit;

    .line 75
    .line 76
    return-object p0
.end method
