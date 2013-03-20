targetdir=../data/red/COSMOS05/OB1_1/

for i in g r i z J H K
do
echo $targetdir$i
ds9 -zscale $targetdir/$i/GROND_"$i"_OB_ana.fits -zoom to fit -colorbar no -geometry 370x620 -regions command "circle 1000 1000 200 # text=$i" -saveimage png $i.png -exit
done
